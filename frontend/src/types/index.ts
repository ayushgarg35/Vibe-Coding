// ─────────────────────────────────────────────────────────────────
// Shared TypeScript types — mirrors backend Pydantic schemas
// ─────────────────────────────────────────────────────────────────

export type DataRegion = "US" | "EU" | "IN";
export type SessionPhase =
  | "discovery" | "gate_1_scope" | "brd" | "gate_2_brd"
  | "prd" | "gate_3_prd" | "frd" | "gate_4_frd"
  | "stories_specs" | "gate_5_stories" | "handoff" | "gate_6_release"
  | "complete" | "paused" | "error";

export type ApprovalStatus = "pending" | "approved" | "revision_requested" | "rejected";
export type ArtifactType = "BRD" | "PRD" | "FRD" | "STORIES" | "SCREEN_SPECS" | "DEVELOPER_HANDOFF" | "REVIEW";
export type ReviewVerdict = "GO" | "REVISE" | "HOLD";
export type ModelTier = "strong" | "medium" | "fast" | "local";

export interface Session {
  session_id: string;
  current_phase: SessionPhase;
  status: string;
  pending_questions: ClarificationQuestion[];
  cost_usd: number;
  created_at: string;
  updated_at: string;
}

export interface ClarificationQuestion {
  question: string;
  why_it_matters: string;
  priority: "must_have" | "nice_to_have";
  options?: string[];
  gap_id?: string;
}

export interface ApprovalGate {
  gate: number;
  title: string;
  artifact?: Record<string, unknown>;
  review_pack?: ReviewPack;
}

export interface ReviewIssue {
  id: string;
  category: string;
  severity: "blocker" | "critical" | "major" | "minor" | "suggestion";
  location: string;
  description: string;
  recommendation: string;
  example_fix?: string;
}

export interface ReviewPack {
  artifact_type: string;
  readiness_score: number;
  verdict: ReviewVerdict;
  confidence: "high" | "medium" | "low";
  summary: string;
  issues: ReviewIssue[];
  blockers: string[];
  recommendations: string[];
}

export interface ModelOption {
  id: string;
  name: string;
  provider: string;
  tier: ModelTier;
  best_for: string[];
}

export interface ArtifactLineage {
  [artifactType: string]: {
    status: "pending" | "completed";
    derived_from?: string[];
  };
}

export interface DecisionLedger {
  decisions: Decision[];
  assumptions: Assumption[];
}

export interface Decision {
  id: string;
  type: "confirmed" | "assumed" | "unresolved";
  category: string;
  statement: string;
  source: string;
  raised_at: string;
  resolved_at?: string;
}

export interface Assumption {
  id: string;
  assumption: string;
  risk_if_wrong?: string;
  status: "active" | "validated" | "invalidated";
}
