-- ═══════════════════════════════════════════════════════════════
-- Agentic PM System — Initial Schema
-- PostgreSQL 16+
-- ═══════════════════════════════════════════════════════════════

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Organisations ────────────────────────────────────────────────
CREATE TABLE organisations (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    slug            TEXT UNIQUE NOT NULL,
    plan            TEXT NOT NULL DEFAULT 'internal',  -- internal | starter | pro | enterprise
    data_region     TEXT NOT NULL DEFAULT 'US',        -- US | EU | IN
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Users ────────────────────────────────────────────────────────
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id          UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    clerk_user_id   TEXT UNIQUE NOT NULL,
    email           TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'pm',  -- pm | po | developer | admin
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Sessions ─────────────────────────────────────────────────────
CREATE TABLE sessions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id          UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
    created_by      UUID NOT NULL REFERENCES users(id),
    product_name    TEXT,
    entry_mode      TEXT NOT NULL DEFAULT 'freeform',  -- freeform | upload | template
    current_phase   TEXT NOT NULL DEFAULT 'discovery',
    status          TEXT NOT NULL DEFAULT 'active',    -- active | paused | complete | archived
    data_region     TEXT NOT NULL DEFAULT 'US',
    total_cost_usd  NUMERIC(10, 6) DEFAULT 0,
    graph_state     JSONB,                             -- LangGraph checkpoint state
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_activity   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Session Participants ─────────────────────────────────────────
CREATE TABLE session_participants (
    session_id      UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role            TEXT NOT NULL DEFAULT 'collaborator',  -- owner | collaborator | reviewer | observer
    joined_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (session_id, user_id)
);

-- ── Decision Ledger ──────────────────────────────────────────────
CREATE TABLE decisions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id      UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    type            TEXT NOT NULL,  -- confirmed | assumed | unresolved
    category        TEXT NOT NULL,  -- scope | persona | integration | compliance | workflow
    statement       TEXT NOT NULL,
    source          TEXT NOT NULL,  -- user_input | agent_inferred | system_default
    raised_by       UUID REFERENCES users(id),
    resolved_by     UUID REFERENCES users(id),
    raised_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at     TIMESTAMPTZ,
    affects_artifacts TEXT[],
    metadata        JSONB
);

-- ── Assumption Register ──────────────────────────────────────────
CREATE TABLE assumptions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id      UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    assumption      TEXT NOT NULL,
    risk_if_wrong   TEXT,
    owner           UUID REFERENCES users(id),
    status          TEXT NOT NULL DEFAULT 'active',  -- active | validated | invalidated
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    validated_at    TIMESTAMPTZ
);

-- ── Artifacts ────────────────────────────────────────────────────
CREATE TABLE artifacts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id      UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    type            TEXT NOT NULL,  -- BRD | PRD | FRD | STORY | AC | SCREEN_SPEC | MATRIX | HANDOFF | REVIEW
    version         TEXT NOT NULL DEFAULT '0.1.0',
    status          TEXT NOT NULL DEFAULT 'draft',  -- draft | in_review | revision_requested | approved | published
    content         JSONB NOT NULL,
    lineage         UUID[],         -- artifact IDs this was derived from
    model_used      TEXT,
    cost_usd        NUMERIC(10, 6) DEFAULT 0,
    created_by      UUID REFERENCES users(id),
    approved_by     UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    approved_at     TIMESTAMPTZ
);

-- ── Approval Gates ───────────────────────────────────────────────
CREATE TABLE approval_gates (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id      UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    gate_number     INTEGER NOT NULL,  -- 1-6
    artifact_ids    UUID[],
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | revision_requested | rejected
    reviewer_id     UUID REFERENCES users(id),
    reviewed_at     TIMESTAMPTZ,
    comments        TEXT,
    redlines        JSONB,             -- structured redline comments
    auto_review_id  UUID REFERENCES artifacts(id),  -- the REVIEW artifact
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(session_id, gate_number)
);

-- ── Audit Log ────────────────────────────────────────────────────
CREATE TABLE audit_log (
    id              BIGSERIAL PRIMARY KEY,
    org_id          UUID REFERENCES organisations(id),
    user_id         UUID REFERENCES users(id),
    session_id      UUID REFERENCES sessions(id),
    action          TEXT NOT NULL,      -- session.created | artifact.approved | gate.rejected | ...
    resource_type   TEXT,
    resource_id     UUID,
    metadata        JSONB,
    ip_address      TEXT,
    user_agent      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Indexes ──────────────────────────────────────────────────────
CREATE INDEX idx_sessions_org_id ON sessions(org_id);
CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_decisions_session_id ON decisions(session_id);
CREATE INDEX idx_assumptions_session_id ON assumptions(session_id);
CREATE INDEX idx_artifacts_session_id ON artifacts(session_id);
CREATE INDEX idx_artifacts_type_status ON artifacts(type, status);
CREATE INDEX idx_approval_gates_session_id ON approval_gates(session_id);
CREATE INDEX idx_audit_log_session_id ON audit_log(session_id);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at);
CREATE INDEX idx_audit_log_org_id ON audit_log(org_id);

-- ── Update timestamp trigger ─────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sessions_updated_at BEFORE UPDATE ON sessions FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_artifacts_updated_at BEFORE UPDATE ON artifacts FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_users_updated_at BEFORE UPDATE ON users FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_orgs_updated_at BEFORE UPDATE ON organisations FOR EACH ROW EXECUTE FUNCTION update_updated_at();
