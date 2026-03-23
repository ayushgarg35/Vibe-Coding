"use client";

import Link from "next/link";
import useSWR from "swr";

const PHASES_ORDERED = [
  "discovery", "brd", "prd", "frd", "stories_specs", "handoff", "complete"
];

const PHASE_LABELS: Record<string, string> = {
  discovery: "Discovery",
  gate_1_scope: "Gate 1: Scope",
  brd: "BRD",
  gate_2_brd: "Gate 2: BRD Review",
  prd: "PRD",
  gate_3_prd: "Gate 3: PRD Review",
  frd: "FRD",
  gate_4_frd: "Gate 4: FRD Review",
  stories_specs: "Stories & Specs",
  gate_5_stories: "Gate 5: Stories Review",
  handoff: "Developer Handoff",
  gate_6_release: "Gate 6: Release Review",
  complete: "Complete",
  paused: "Paused",
};

function PhaseBadge({ phase }: { phase: string }) {
  const isGate = phase.startsWith("gate_");
  const isComplete = phase === "complete";
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
      isComplete ? "bg-green-900 text-green-300" :
      isGate ? "bg-yellow-900 text-yellow-300" :
      "bg-blue-900 text-blue-300"
    }`}>
      {PHASE_LABELS[phase] || phase}
    </span>
  );
}

export default function DashboardPage() {
  // TODO: Fetch real sessions from API with Clerk auth
  const mockSessions = [
    { session_id: "abc-123", product_name: "Leave Management System", current_phase: "gate_2_brd", cost_usd: 0.42, updated_at: "2026-03-23T10:00:00Z" },
    { session_id: "def-456", product_name: "Customer Portal v2", current_phase: "frd", cost_usd: 1.15, updated_at: "2026-03-22T15:30:00Z" },
    { session_id: "ghi-789", product_name: "Inventory Module", current_phase: "complete", cost_usd: 3.82, updated_at: "2026-03-21T09:15:00Z" },
  ];

  return (
    <div className="min-h-screen p-8">
      <div className="max-w-5xl mx-auto space-y-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-white">Sessions</h1>
            <p className="text-sm text-gray-500 mt-1">Product artifact pipelines</p>
          </div>
          <Link
            href="/sessions/new"
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            + New Session
          </Link>
        </div>

        <div className="space-y-3">
          {mockSessions.map((session) => (
            <Link
              key={session.session_id}
              href={`/sessions/${session.session_id}`}
              className="block p-4 rounded-lg border border-gray-800 hover:border-gray-600 bg-gray-900 transition-colors"
            >
              <div className="flex items-center justify-between">
                <div className="space-y-1">
                  <div className="font-medium text-white">{session.product_name}</div>
                  <div className="flex items-center gap-3">
                    <PhaseBadge phase={session.current_phase} />
                    <span className="text-xs text-gray-600">
                      ${session.cost_usd.toFixed(2)} LLM cost
                    </span>
                  </div>
                </div>
                <div className="text-xs text-gray-600">
                  {new Date(session.updated_at).toLocaleDateString()}
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
