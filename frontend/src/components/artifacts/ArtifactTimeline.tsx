"use client";

/**
 * ArtifactTimeline — visualises the artifact pipeline progress.
 * Shows which stages are complete, in-progress, at a gate, or pending.
 */
import type { ArtifactLineage, SessionPhase } from "@/types";

const PIPELINE_STEPS = [
  { key: "discovery", label: "Discovery", icon: "?" },
  { key: "BRD", label: "BRD", icon: "B" },
  { key: "PRD", label: "PRD", icon: "P" },
  { key: "FRD", label: "FRD", icon: "F" },
  { key: "STORIES", label: "Stories", icon: "S" },
  { key: "DEVELOPER_HANDOFF", label: "Handoff", icon: "H" },
];

const GATE_PHASES = new Set([
  "gate_1_scope", "gate_2_brd", "gate_3_prd", "gate_4_frd",
  "gate_5_stories", "gate_6_release",
]);

interface ArtifactTimelineProps {
  currentPhase: SessionPhase;
  lineage?: ArtifactLineage;
}

export function ArtifactTimeline({ currentPhase, lineage }: ArtifactTimelineProps) {
  const isAtGate = GATE_PHASES.has(currentPhase);

  return (
    <div className="flex items-center gap-1">
      {PIPELINE_STEPS.map((step, i) => {
        const status = lineage?.[step.key]?.status;
        const isCompleted = status === "completed";
        const isCurrent = currentPhase.includes(step.key.toLowerCase());
        const isGateCurrent = isAtGate && i === getCurrentGateIndex(currentPhase);

        return (
          <div key={step.key} className="flex items-center gap-1">
            {i > 0 && (
              <div className={`h-px w-6 ${isCompleted ? "bg-blue-500" : "bg-gray-800"}`} />
            )}
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold transition-all ${
                isCompleted
                  ? "bg-blue-600 text-white"
                  : isGateCurrent
                  ? "bg-yellow-600 text-white ring-2 ring-yellow-400"
                  : isCurrent
                  ? "bg-gray-700 text-white ring-2 ring-blue-400"
                  : "bg-gray-900 text-gray-600 border border-gray-800"
              }`}
              title={step.label}
            >
              {isCompleted ? "✓" : step.icon}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function getCurrentGateIndex(phase: SessionPhase): number {
  const gateMap: Record<string, number> = {
    gate_1_scope: 0,
    gate_2_brd: 1,
    gate_3_prd: 2,
    gate_4_frd: 3,
    gate_5_stories: 4,
    gate_6_release: 5,
  };
  return gateMap[phase] ?? -1;
}
