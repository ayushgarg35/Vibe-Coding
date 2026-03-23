/**
 * API client — all backend calls go through here.
 * Automatically includes auth headers and data region.
 */
import type {
  ApprovalStatus,
  ArtifactLineage,
  ArtifactType,
  DataRegion,
  DecisionLedger,
  ReviewPack,
  Session,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(
  path: string,
  options: RequestInit & { region?: DataRegion } = {}
): Promise<T> {
  const { region = "US", ...fetchOptions } = options;

  const res = await fetch(`${API_BASE}${path}`, {
    ...fetchOptions,
    headers: {
      "Content-Type": "application/json",
      "X-Data-Region": region,
      // TODO: Add Clerk auth token here
      // "Authorization": `Bearer ${await getToken()}`,
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
  create: (data: {
    product_description: string;
    entry_mode?: string;
    data_region?: DataRegion;
    model_overrides?: Record<string, string>;
  }) =>
    request<Session>("/api/v1/sessions/", {
      method: "POST",
      body: JSON.stringify(data),
      region: data.data_region,
    }),

  get: (sessionId: string, region?: DataRegion) =>
    request<Session>(`/api/v1/sessions/${sessionId}`, { region }),

  submitAnswers: (sessionId: string, answers: Record<string, string>, region?: DataRegion) =>
    request<Session>(`/api/v1/sessions/${sessionId}/answer`, {
      method: "POST",
      body: JSON.stringify(answers),
      region,
    }),
};

// ── Approvals ─────────────────────────────────────────────────────

export const approvals = {
  submitGateDecision: (
    sessionId: string,
    gateNumber: number,
    data: { status: ApprovalStatus; comments?: string; redlines?: unknown[] },
    region?: DataRegion
  ) =>
    request(`/api/v1/approvals/${sessionId}/gate/${gateNumber}`, {
      method: "POST",
      body: JSON.stringify(data),
      region,
    }),

  getReviewPack: (sessionId: string, gateNumber: number, region?: DataRegion) =>
    request<{ review_pack: ReviewPack }>(
      `/api/v1/approvals/${sessionId}/gate/${gateNumber}/review-pack`,
      { region }
    ),
};

// ── Artifacts ─────────────────────────────────────────────────────

export const artifacts = {
  get: (sessionId: string, artifactType: ArtifactType, region?: DataRegion) =>
    request<{ content: unknown }>(`/api/v1/artifacts/${sessionId}/${artifactType}`, { region }),

  getLineage: (sessionId: string, region?: DataRegion) =>
    request<{ lineage: ArtifactLineage }>(`/api/v1/artifacts/${sessionId}/lineage`, { region }),

  getDecisions: (sessionId: string, region?: DataRegion) =>
    request<DecisionLedger>(`/api/v1/artifacts/${sessionId}/decisions`, { region }),
};

// ── Review ────────────────────────────────────────────────────────

export const review = {
  standalone: (data: {
    artifact_type: string;
    artifact_content: unknown;
    prior_artifacts?: unknown;
    data_region?: DataRegion;
    model_override?: string;
  }) =>
    request<{ review_pack: ReviewPack }>("/api/v1/review/standalone", {
      method: "POST",
      body: JSON.stringify(data),
      region: data.data_region,
    }),
};

// ── Models ────────────────────────────────────────────────────────

export const models = {
  list: () => request<{ models: unknown[] }>("/api/v1/models/available"),
  getRoutingPolicy: () => request("/api/v1/models/routing-policy"),
  getRegionConstraints: (region: DataRegion) =>
    request(`/api/v1/models/region-constraints/${region}`),
};
