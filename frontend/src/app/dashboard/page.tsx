"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useEffect, useState } from "react";

import { ArtifactTimeline } from "@/components/artifacts/ArtifactTimeline";
import { sessions } from "@/lib/api";
import type { Session, SessionPhase } from "@/types";

const PHASE_LABELS: Record<string, string> = {
  discovery: "Discovery", gate_1_scope: "Awaiting Scope Approval",
  brd: "Generating BRD", gate_2_brd: "Awaiting BRD Approval",
  prd: "Generating PRD", gate_3_prd: "Awaiting PRD Approval",
  frd: "Generating FRD", gate_4_frd: "Awaiting FRD Approval",
  stories_specs: "Generating Stories", gate_5_stories: "Awaiting Stories Approval",
  handoff: "Assembling Handoff", gate_6_release: "Awaiting Release Sign-off",
  complete: "Complete", paused: "Paused", error: "Error",
};

const PHASE_BADGE_STYLE: Record<string, string> = {
  complete: "bg-green-900/50 text-green-300",
  error: "bg-red-900/50 text-red-300",
  paused: "bg-gray-800 text-gray-400",
};

function getPhaseBadgeStyle(phase: string): string {
  if (PHASE_BADGE_STYLE[phase]) return PHASE_BADGE_STYLE[phase];
  if (phase.startsWith("gate_")) return "bg-yellow-900/50 text-yellow-300";
  return "bg-blue-900/50 text-blue-300";
}

export default function DashboardPage() {
  const { getToken } = useAuth();
  const [sessionList, setSessionList] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      const token = await getToken();
      if (!token) return;
      try {
        const data = await sessions.list(token);
        setSessionList(Array.isArray(data) ? data : []);
      } catch {
        setSessionList([]);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [getToken]);

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-5xl mx-auto space-y-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Sessions</h1>
            <p className="text-sm text-gray-500 mt-1">Your product artifact pipelines</p>
          </div>
          <Link
            href="/sessions/new"
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            + New Session
          </Link>
        </div>

        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-20 rounded-lg bg-gray-900 border border-gray-800 animate-pulse" />
            ))}
          </div>
        ) : sessionList.length === 0 ? (
          <div className="text-center py-20 space-y-4">
            <div className="text-gray-600 text-lg">No sessions yet</div>
            <Link href="/sessions/new" className="text-blue-400 hover:text-blue-300 text-sm">
              Start your first session →
            </Link>
          </div>
        ) : (
          <div className="space-y-3">
            {sessionList.map((session) => (
              <Link
                key={session.session_id}
                href={`/sessions/${session.session_id}`}
                className="block p-4 rounded-lg border border-gray-800 hover:border-gray-600 bg-gray-900 transition-colors"
              >
                <div className="flex items-center justify-between gap-4">
                  <div className="min-w-0 space-y-2">
                    <div className="font-medium text-white truncate">
                      {session.product_name || "Untitled Session"}
                    </div>
                    <div className="flex items-center gap-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${getPhaseBadgeStyle(session.current_phase)}`}>
                        {PHASE_LABELS[session.current_phase] || session.current_phase}
                      </span>
                      <span className="text-xs text-gray-600">
                        ${session.cost_usd.toFixed(4)} LLM cost
                      </span>
                    </div>
                  </div>
                  <ArtifactTimeline currentPhase={session.current_phase as SessionPhase} />
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
