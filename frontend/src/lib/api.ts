/**
 * API client — all backend calls go through here.
 * Automatically attaches Clerk auth token and data region header.
 */
import { auth } from "@clerk/nextjs/server";
import type {
  ApprovalStatus,
  ArtifactLineage,
  ArtifactType,
  DataRegion,
  DecisionLedger,
  ModelOption,
  ReviewPack,
  Session,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function getAuthHeader(): Promise<string> {
  try {
    // Server-side: use Clerk's server auth
    const { getToken } = auth();
    const token = await getToken();
    return token ? `Bearer ${token}` : "";
  } catch {
    // Client-side: token fetched via useAuth hook — handled by caller
    return "";
  }
}

async function request<T>(
  path: string,
  options: RequestInit & { region?: DataRegion; token?: string } = {}
): Promise<T> {
  const { region = "US", token, ...fetchOptions } = options;

  const authHeader = token ? `Bearer ${token}` : await getAuthHeader();

  const res = await fetch(`${API_BASE}${path}`, {
    ...fetchOptions,
    headers: {
      "Content-Type": "application/json",
      "X-Data-Region": region,
      ...(authHeader ? { Authorization: authHeader } : {}),
      ...fetchOptions.headers,
    },
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || `API error ${res.status}`);
  }

  return res.json();
}

// ── Sessions ──────────────────────────────────────────────────────

export const sessions = {
  create: (
    data: { product_description: string; entry_mode?: string; model_overrides?: Record<string, string> },
    token: string,
    region?: DataRegion
  ) =>
    request<Session>("/api/v1/sessions/", {
      method: "POST",
      body: JSON.stringify(data),
      token,
      region,
    }),

  list: (token: string, region?: DataRegion) =>
    request<Session[]>("/api/v1/sessions/", { token, region }),

  get: (sessionId: string, token: string, region?: DataRegion) =>
    request<Session>(`/api/v1/sessions/${sessionId}`, { token, region }),

  submitAnswers: (
    sessionId: string,
    answers: Record<string, string>,
    token: string,
    region?: DataRegion
  ) =>
    request<{ current_phase: string; pending_questions: unknown[]; confirmed_facts: unknown }>(
      `/api/v1/sessions/${sessionId}/answer`,
      { method: "POST", body: JSON.stringify({ answers }), token, region }
    ),
};

// ── Approvals ─────────────────────────────────────────────────────

export const approvals = {
  submitGateDecision: (
    sessionId: string,
    gateNumber: number,
    data: { status: ApprovalStatus; comments?: string; redlines?: unknown[]; model_overrides?: Record<string, string> },
    token: string,
    region?: DataRegion
  ) =>
    request<{ current_phase: string; next_artifact: string }>(
      `/api/v1/approvals/${sessionId}/gate/${gateNumber}`,
      { method: "POST", body: JSON.stringify(data), token, region }
    ),

  getReviewPack: (sessionId: string, gateNumber: number, token: string, region?: DataRegion) =>
    request<{ review_pack: ReviewPack }>(
      `/api/v1/approvals/${sessionId}/gate/${gateNumber}/review-pack`,
      { token, region }
    ),

  getAllGates: (sessionId: string, token: string, region?: DataRegion) =>
    request<{ gates: unknown[] }>(`/api/v1/approvals/${sessionId}/gates`, { token, region }),
};

// ── Artifacts ─────────────────────────────────────────────────────

export const artifacts = {
  get: (sessionId: string, artifactType: ArtifactType, token: string, region?: DataRegion) =>
    request<{ content: unknown }>(`/api/v1/artifacts/${sessionId}/${artifactType}`, { token, region }),

  getLineage: (sessionId: string, token: string, region?: DataRegion) =>
    request<{ lineage: ArtifactLineage }>(`/api/v1/artifacts/${sessionId}/lineage`, { token, region }),

  getDecisions: (sessionId: string, token: string, region?: DataRegion) =>
    request<DecisionLedger>(`/api/v1/artifacts/${sessionId}/decisions`, { token, region }),
};

// ── Review ────────────────────────────────────────────────────────

export const review = {
  standalone: (
    data: { artifact_type: string; artifact_content: unknown; prior_artifacts?: unknown; data_region?: DataRegion; model_override?: string },
    token: string
  ) =>
    request<{ review_pack: ReviewPack }>("/api/v1/review/standalone", {
      method: "POST",
      body: JSON.stringify(data),
      token,
      region: data.data_region,
    }),
};

// ── Models ────────────────────────────────────────────────────────

export const models = {
  list: (token: string) =>
    request<{ models: ModelOption[] }>("/api/v1/models/available", { token }),
  getRoutingPolicy: (token: string) =>
    request("/api/v1/models/routing-policy", { token }),
  getRegionConstraints: (region: DataRegion, token: string) =>
    request(`/api/v1/models/region-constraints/${region}`, { token }),
};
