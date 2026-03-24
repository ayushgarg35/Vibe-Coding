"use client";

/**
 * Session View — the main workspace for a product session.
 * Shows: pipeline timeline, agent conversation, approval gates, artifacts, model picker.
 * Streams agent output in real time via SSE.
 */
import { useAuth } from "@clerk/nextjs";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { ApprovalGate } from "@/components/approval/ApprovalGate";
import { ArtifactTimeline } from "@/components/artifacts/ArtifactTimeline";
import { ModelPicker } from "@/components/chat/ModelPicker";
import { approvals, artifacts, models, sessions } from "@/lib/api";
import { createSessionStream } from "@/lib/websocket";
import type {
  ApprovalStatus,
  ArtifactLineage,
  ClarificationQuestion,
  ModelOption,
  ReviewPack,
  SessionPhase,
} from "@/types";

const GATE_PHASES: Record<string, number> = {
  gate_1_scope: 1, gate_2_brd: 2, gate_3_prd: 3,
  gate_4_frd: 4, gate_5_stories: 5, gate_6_release: 6,
};

const GATE_TITLES: Record<number, string> = {
  1: "Gate 1 — Scope Approval",
  2: "Gate 2 — BRD Review",
  3: "Gate 3 — PRD Review",
  4: "Gate 4 — FRD Review",
  5: "Gate 5 — Stories & Specs Review",
  6: "Gate 6 — Release Readiness",
};

interface Message {
  id: string;
  role: "user" | "agent" | "system";
  content: string;
  agent?: string;
  model?: string;
  streaming?: boolean;
}

interface SessionState {
  phase: SessionPhase;
  productName?: string;
  pendingQuestions: ClarificationQuestion[];
  costUsd: number;
  lineage?: ArtifactLineage;
}

export default function SessionPage({ params }: { params: { id: string } }) {
  const { getToken } = useAuth();
  const sessionId = params.id;

  const [sessionState, setSessionState] = useState<SessionState>({
    phase: "discovery",
    pendingQuestions: [],
    costUsd: 0,
  });
  const [messages, setMessages] = useState<Message[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [availableModels, setAvailableModels] = useState<ModelOption[]>([]);
  const [modelOverrides, setModelOverrides] = useState<Record<string, string>>({});
  const [reviewPack, setReviewPack] = useState<ReviewPack | null>(null);
  const [activeArtifact, setActiveArtifact] = useState<string | null>(null);
  const [artifactContent, setArtifactContent] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const streamCleanupRef = useRef<(() => void) | null>(null);

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });

  // ── Load initial session state ─────────────────────────────────
  useEffect(() => {
    const load = async () => {
      const token = await getToken();
      if (!token) return;

      try {
        const [session, lineage] = await Promise.all([
          sessions.get(sessionId, token),
          artifacts.getLineage(sessionId, token).catch(() => ({ lineage: {} })),
        ]);
        setSessionState({
          phase: session.current_phase as SessionPhase,
          productName: session.product_name ?? undefined,
          pendingQuestions: session.pending_questions,
          costUsd: session.cost_usd,
          lineage: lineage.lineage,
        });

        // Load review pack if at a gate
        const gateNum = GATE_PHASES[session.current_phase];
        if (gateNum && gateNum >= 2) {
          const rp = await approvals.getReviewPack(sessionId, gateNum, token).catch(() => null);
          if (rp) setReviewPack(rp.review_pack);
        }
      } catch (e) {
        toast.error("Failed to load session");
      }
    };
    load();
  }, [sessionId, getToken]);

  // ── Load available models ───────────────────────────────────────
  useEffect(() => {
    const load = async () => {
      const token = await getToken();
      if (!token) return;
      const { models: m } = await models.list(token).catch(() => ({ models: [] }));
      setAvailableModels(m);
    };
    load();
  }, [getToken]);

  // ── SSE stream ─────────────────────────────────────────────────
  useEffect(() => {
    streamCleanupRef.current = createSessionStream(
      sessionId,
      (event) => {
        if (event.type === "agent_start") {
          setMessages((prev) => [
            ...prev,
            { id: `${event.agent}-${Date.now()}`, role: "agent", content: "", agent: event.agent, streaming: true },
          ]);
        }
        if (event.type === "agent_token") {
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.streaming) {
              return [...prev.slice(0, -1), { ...last, content: last.content + (event.token || "") }];
            }
            return prev;
          });
        }
        if (event.type === "agent_complete") {
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last?.streaming) return [...prev.slice(0, -1), { ...last, streaming: false }];
            return prev;
          });
        }
        if (event.type === "gate_reached") {
          const gateNum = (event.data as { gate?: number })?.gate;
          if (gateNum) loadReviewPack(gateNum);
        }
        scrollToBottom();
      }
    );
    return () => streamCleanupRef.current?.();
  }, [sessionId]);

  const loadReviewPack = async (gateNumber: number) => {
    const token = await getToken();
    if (!token) return;
    const rp = await approvals.getReviewPack(sessionId, gateNumber, token).catch(() => null);
    if (rp) setReviewPack(rp.review_pack);
  };

  // ── Submit clarification answers ───────────────────────────────
  const submitAnswers = async () => {
    const token = await getToken();
    if (!token) return;
    setLoading(true);

    setMessages((prev) => [
      ...prev,
      { id: `user-${Date.now()}`, role: "user", content: JSON.stringify(answers, null, 2) },
    ]);

    try {
      const result = await sessions.submitAnswers(sessionId, answers, token);
      setSessionState((prev) => ({
        ...prev,
        phase: result.current_phase as SessionPhase,
        pendingQuestions: (result.pending_questions || []) as ClarificationQuestion[],
      }));
      setAnswers({});
    } catch (e) {
      toast.error("Failed to submit answers");
    } finally {
      setLoading(false);
    }
  };

  // ── Gate approval ──────────────────────────────────────────────
  const handleGateDecision = useCallback(
    async (status: ApprovalStatus, comments: string) => {
      const token = await getToken();
      if (!token) return;

      const gateNum = GATE_PHASES[sessionState.phase];
      if (!gateNum) return;

      const result = await approvals.submitGateDecision(
        sessionId,
        gateNum,
        { status, comments, model_overrides: modelOverrides },
        token
      );

      setSessionState((prev) => ({ ...prev, phase: result.current_phase as SessionPhase }));
      setReviewPack(null);

      setMessages((prev) => [
        ...prev,
        {
          id: `gate-${Date.now()}`,
          role: "system",
          content: `Gate ${gateNum} ${status.replace("_", " ")}. ${result.next_artifact ? `Next: ${result.next_artifact}` : ""}`,
        },
      ]);
    },
    [sessionId, sessionState.phase, modelOverrides, getToken]
  );

  // ── Load artifact ──────────────────────────────────────────────
  const loadArtifact = async (type: string) => {
    const token = await getToken();
    if (!token) return;
    setActiveArtifact(type);
    try {
      const result = await artifacts.get(sessionId, type as any, token);
      setArtifactContent(result.content);
    } catch {
      setArtifactContent(null);
      toast.error(`${type} not available yet`);
    }
  };

  const isAtGate = sessionState.phase in GATE_PHASES;
  const gateNumber = GATE_PHASES[sessionState.phase];
  const hasPendingQuestions = sessionState.pendingQuestions.length > 0;

  return (
    <div className="h-screen flex flex-col bg-gray-950">
      {/* ── Header ─────────────────────────────────────────────── */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-gray-800 shrink-0">
        <div className="flex items-center gap-4">
          <a href="/dashboard" className="text-gray-600 hover:text-gray-300 text-sm">← Dashboard</a>
          <div>
            <h1 className="font-semibold text-white text-sm">
              {sessionState.productName || "Untitled Session"}
            </h1>
            <p className="text-xs text-gray-600">{sessionId}</p>
          </div>
        </div>
        <ArtifactTimeline currentPhase={sessionState.phase} lineage={sessionState.lineage} />
        <div className="text-xs text-gray-600">${sessionState.costUsd.toFixed(4)} LLM cost</div>
      </header>

      {/* ── Main layout ────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0">
        {/* Left: conversation + interaction panel */}
        <div className="flex flex-col w-1/2 border-r border-gray-800">
          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.map((msg) => (
              <MessageBubble key={msg.id} message={msg} />
            ))}
            <div ref={messagesEndRef} />
          </div>

          {/* Interaction panel */}
          <div className="border-t border-gray-800 p-4 space-y-4 shrink-0">
            {/* Clarification questions */}
            {hasPendingQuestions && !isAtGate && (
              <ClarificationPanel
                questions={sessionState.pendingQuestions}
                answers={answers}
                onAnswer={(q, a) => setAnswers((prev) => ({ ...prev, [q]: a }))}
                onSubmit={submitAnswers}
                loading={loading}
                availableModels={availableModels}
                modelOverrides={modelOverrides}
                onModelChange={(task, model) => setModelOverrides((prev) => ({ ...prev, [task]: model }))}
              />
            )}

            {/* Gate approval panel */}
            {isAtGate && (
              <ApprovalGate
                sessionId={sessionId}
                gateNumber={gateNumber}
                gateTitle={GATE_TITLES[gateNumber]}
                reviewPack={reviewPack ?? undefined}
                onDecision={handleGateDecision}
              />
            )}

            {/* Idle state */}
            {!hasPendingQuestions && !isAtGate && (
              <div className="text-center text-gray-600 text-sm py-4">
                {sessionState.phase === "complete"
                  ? "Session complete — developer handoff is ready."
                  : "Agents are working..."}
              </div>
            )}
          </div>
        </div>

        {/* Right: artifact viewer */}
        <div className="flex flex-col w-1/2">
          {/* Artifact tabs */}
          <div className="flex border-b border-gray-800 px-4 shrink-0">
            {(["BRD", "PRD", "FRD", "STORIES", "DEVELOPER_HANDOFF"] as const).map((type) => {
              const available = sessionState.lineage?.[type]?.status === "completed";
              return (
                <button
                  key={type}
                  onClick={() => available && loadArtifact(type)}
                  className={`px-4 py-3 text-xs font-medium border-b-2 transition-colors ${
                    activeArtifact === type
                      ? "border-blue-500 text-white"
                      : available
                      ? "border-transparent text-gray-500 hover:text-gray-300"
                      : "border-transparent text-gray-700 cursor-not-allowed"
                  }`}
                >
                  {type.replace("_", " ")}
                </button>
              );
            })}
          </div>

          {/* Artifact content */}
          <div className="flex-1 overflow-y-auto p-4">
            {activeArtifact && artifactContent ? (
              <ArtifactViewer type={activeArtifact} content={artifactContent} />
            ) : (
              <div className="flex items-center justify-center h-full text-gray-700 text-sm">
                Select an artifact to view
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────────

function MessageBubble({ message }: { message: Message }) {
  const styles = {
    user: "bg-blue-900/30 border-blue-800 ml-8",
    agent: "bg-gray-900 border-gray-800 mr-8",
    system: "bg-gray-900/50 border-gray-800/50 text-center mx-8",
  };
  return (
    <div className={`p-3 rounded-lg border text-sm ${styles[message.role]}`}>
      {message.agent && (
        <div className="text-xs text-gray-500 mb-1 font-medium">
          {message.agent.replace("_", " ").toUpperCase()}
          {message.model && <span className="text-gray-700 ml-2">· {message.model}</span>}
        </div>
      )}
      <div className="text-gray-300 whitespace-pre-wrap">
        {message.content}
        {message.streaming && <span className="animate-pulse">▌</span>}
      </div>
    </div>
  );
}

function ClarificationPanel({
  questions, answers, onAnswer, onSubmit, loading,
  availableModels, modelOverrides, onModelChange,
}: {
  questions: ClarificationQuestion[];
  answers: Record<string, string>;
  onAnswer: (q: string, a: string) => void;
  onSubmit: () => void;
  loading: boolean;
  availableModels: ModelOption[];
  modelOverrides: Record<string, string>;
  onModelChange: (task: string, model: string) => void;
}) {
  const blockers = questions.filter((q) => q.priority === "must_have");
  const nicToHave = questions.filter((q) => q.priority === "nice_to_have");
  const allBlockersAnswered = blockers.every((q) => answers[q.question]?.trim());

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium text-white">
          Clarification needed ({blockers.length} required)
        </div>
        <ModelPicker
          taskType="intake_conversation"
          currentModel={modelOverrides["intake_conversation"] || "claude-sonnet-4-6"}
          availableModels={availableModels}
          onSelect={onModelChange}
        />
      </div>

      <div className="space-y-3 max-h-64 overflow-y-auto">
        {[...blockers, ...nicToHave].map((q) => (
          <div key={q.question} className="space-y-1">
            <div className="flex items-start gap-2">
              <span className={`text-xs mt-0.5 shrink-0 ${q.priority === "must_have" ? "text-red-400" : "text-gray-600"}`}>
                {q.priority === "must_have" ? "Required" : "Optional"}
              </span>
              <div>
                <div className="text-sm text-gray-300">{q.question}</div>
                {q.why_it_matters && (
                  <div className="text-xs text-gray-600 mt-0.5">{q.why_it_matters}</div>
                )}
              </div>
            </div>
            {q.options && q.options.length > 0 ? (
              <div className="flex flex-wrap gap-2 pl-14">
                {q.options.map((opt) => (
                  <button
                    key={opt}
                    onClick={() => onAnswer(q.question, opt)}
                    className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                      answers[q.question] === opt
                        ? "bg-blue-600 border-blue-500 text-white"
                        : "border-gray-700 text-gray-400 hover:border-gray-500"
                    }`}
                  >
                    {opt}
                  </button>
                ))}
                <button
                  onClick={() => onAnswer(q.question, "you decide")}
                  className="text-xs px-3 py-1 rounded-full border border-gray-800 text-gray-600 hover:border-gray-600"
                >
                  You decide
                </button>
              </div>
            ) : (
              <input
                className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-1.5 text-sm text-gray-200 placeholder-gray-600 focus:outline-none focus:border-gray-500 ml-14"
                placeholder="Your answer..."
                value={answers[q.question] || ""}
                onChange={(e) => onAnswer(q.question, e.target.value)}
              />
            )}
          </div>
        ))}
      </div>

      <button
        onClick={onSubmit}
        disabled={!allBlockersAnswered || loading}
        className="w-full py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-40"
      >
        {loading ? "Processing..." : "Continue →"}
      </button>
    </div>
  );
}

function ArtifactViewer({ type, content }: { type: string; content: unknown }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white">{type.replace("_", " ")}</h2>
        <button
          onClick={() => {
            const blob = new Blob([JSON.stringify(content, null, 2)], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `${type.toLowerCase()}.json`;
            a.click();
          }}
          className="text-xs text-gray-600 hover:text-gray-300"
        >
          Export JSON
        </button>
      </div>
      <pre className="text-xs text-gray-400 bg-gray-900 rounded-lg p-4 overflow-auto whitespace-pre-wrap">
        {JSON.stringify(content, null, 2)}
      </pre>
    </div>
  );
}
