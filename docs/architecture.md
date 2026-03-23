# System Architecture

## Overview

The Agentic PM System is a stage-gated, model-agnostic product management platform.
It conducts interactive product discovery, generates BRD/PRD/FRD and related artifacts,
and reviews them with PO-quality automated checks — with human approval at every gate.

## Core Design Principles

1. **Interactive over one-shot** — never assumes the full product from a single prompt
2. **Stage-gated** — 6 human approval gates; nothing advances without sign-off
3. **Traceable** — every artifact element links to a source decision or user input
4. **Model-agnostic** — LiteLLM routes tasks to the best model; users can override inline
5. **Compliance-first** — SOC2, GDPR, DPDPA baked in from day one

## Agent Graph (LangGraph)

```
START → Intake → Gap Detection → [Clarification Loop] → Gate 1
→ BRD → PO Review → Gate 2
→ PRD → PO Review → Gate 3
→ FRD → PO Review → Gate 4
→ Stories + Specs (parallel) → PO Review → Gate 5
→ Handoff Pack → PO Review → Gate 6
→ END
```

Revision loops at each gate: if rejected, returns to the previous generation node.

## Key Components

| Component | Technology | Purpose |
|---|---|---|
| Backend | FastAPI + Python | API, WebSocket, agent orchestration host |
| Orchestrator | LangGraph | Stateful multi-agent workflow with human interrupts |
| LLM Abstraction | LiteLLM | Model-agnostic routing, 100+ providers |
| PII Guard | Presidio | Compliance — strips PII before every LLM call |
| Primary DB | PostgreSQL | Sessions, artifacts, decisions, audit log |
| Checkpoint Store | PostgreSQL (LangGraph) | Graph state persistence for resumable sessions |
| Vector Store | Qdrant | RAG over uploaded documents and prior artifacts |
| Cache/Queue | Redis + Celery | Async agent tasks, session pub/sub |
| Object Storage | S3 (MinIO local) | Artifact file storage, exported documents |
| Frontend | Next.js 14 | App Router, SSE streaming, Yjs real-time collab |
| Auth | Clerk | JWT auth, org management, multi-tenancy ready |
| Collab | Yjs + y-websocket | Real-time collaborative artifact editing |
| Observability | LangSmith + Prometheus | Agent tracing, cost tracking, infra metrics |

## Data Flow

```
User Input
    ↓
RegionGuardMiddleware (tag data region)
    ↓
AuditLogMiddleware (log request)
    ↓
FastAPI Route Handler
    ↓
LangGraph Orchestrator (load state from PostgreSQL checkpointer)
    ↓
Specialist Agent
    ↓
PIIGuard (anonymize PII)
    ↓
LiteLLM Adapter (route to correct model per policy)
    ↓
LLM Provider (Anthropic / OpenAI / Azure / Google)
    ↓
Structured Response → Update Graph State → Persist to PostgreSQL
    ↓
SSE Stream → Frontend
```

## Compliance Architecture

- **PII Guard**: Presidio-based NLP + rule-based detection; runs before every LLM call
- **Region Guard**: Middleware tags every request with data region (US/EU/IN)
- **LLM Routing**: Denies non-compliant providers per region (e.g., no OpenAI for EU without Azure)
- **Audit Log**: Every API request + approval decision + artifact change logged to `audit_log` table
- **Data Residency**: PostgreSQL and S3 deployable per-region; documented in infra runbook
- **Right to Erasure**: TODO — implement `/api/v1/gdpr/erase/{user_id}` endpoint
- **Consent**: TODO — wire Clerk metadata for GDPR/DPDPA consent tracking

## Scaling Path (Internal → SaaS)

| Concern | Internal MVP | SaaS |
|---|---|---|
| Auth | Single org (Clerk) | Multi-tenant orgs (Clerk) |
| Data isolation | DB-level org_id filtering | Row-level security in PostgreSQL |
| Real-time collab | Async handoff | Yjs + y-websocket |
| Billing | None | Stripe + per-org cost tracking |
| Deployment | Docker Compose | Kubernetes + Helm |
| LLM cost | Per-session tracking | Per-org budgets + billing integration |
