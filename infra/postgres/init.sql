-- SignalCare Agentic Demo — Initial Schema
-- Week 1 skeleton. Expanded in Week 2 (audit, prompts) and Week 4 (evidence).

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ---------- L0: Prompt Registry ----------
CREATE TABLE IF NOT EXISTS prompts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    key TEXT NOT NULL,
    version TEXT NOT NULL,
    hash TEXT NOT NULL,
    body TEXT NOT NULL,
    model_tier TEXT NOT NULL CHECK (model_tier IN ('reasoning', 'balanced', 'fast')),
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (key, version)
);

-- ---------- L0: Ground-truth store ----------
CREATE TABLE IF NOT EXISTS ground_truth (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_name TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    input JSONB NOT NULL,
    ai_output JSONB NOT NULL,
    human_action TEXT NOT NULL CHECK (human_action IN ('accept', 'edit', 'reject')),
    human_output JSONB,
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------- L7: Audit (append-only) ----------
CREATE TABLE IF NOT EXISTS audit_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trace_id TEXT,
    actor_type TEXT NOT NULL CHECK (actor_type IN ('user', 'agent', 'system')),
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    details JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_audit_created ON audit_events(created_at);
CREATE INDEX IF NOT EXISTS ix_audit_entity ON audit_events(entity_type, entity_id);

-- ---------- L7: Referrals (minimal for demo) ----------
CREATE TABLE IF NOT EXISTS referrals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    workflow_state TEXT NOT NULL DEFAULT 'New',
    form_data JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------- Agent Registry ----------
CREATE TABLE IF NOT EXISTS agents (
    name TEXT PRIMARY KEY,
    model_tier TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    tools JSONB NOT NULL DEFAULT '[]',
    feature_flag TEXT NOT NULL,
    phi_touching BOOLEAN NOT NULL DEFAULT FALSE,
    requires_hitl BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB NOT NULL DEFAULT '{}'
);

-- ---------- Feature Readiness Registry ----------
CREATE TABLE IF NOT EXISTS feature_registry (
    capability_key TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('not_started','planned','in_progress','configured','live','degraded','disabled','retired')),
    evidence TEXT,
    owner TEXT,
    role_scope JSONB DEFAULT '[]',
    workflow_scope JSONB DEFAULT '[]',
    risk_level TEXT,
    customer_visibility TEXT,
    last_verified TIMESTAMPTZ
);

-- ---------- L2B: Evidence Fabric (Week 4) ----------
CREATE TABLE IF NOT EXISTS evidence_objects (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL,
    referral_id UUID REFERENCES referrals(id),
    document_id TEXT NOT NULL,
    document_version INT NOT NULL DEFAULT 1,
    document_type TEXT,
    source_channel TEXT,
    content_hash TEXT NOT NULL,
    raw_ocr_text TEXT,
    verification_status TEXT DEFAULT 'unverified',
    verifier_id TEXT,
    verified_at TIMESTAMPTZ,
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_evidence_hash ON evidence_objects(content_hash);
CREATE INDEX IF NOT EXISTS ix_evidence_referral ON evidence_objects(referral_id);

CREATE TABLE IF NOT EXISTS fact_records (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    evidence_id UUID NOT NULL REFERENCES evidence_objects(id) ON DELETE CASCADE,
    fact_type TEXT NOT NULL,
    fact_value TEXT NOT NULL,
    source_page INT,
    source_section TEXT,
    source_bbox JSONB,
    confidence REAL NOT NULL,
    extraction_method TEXT,
    verifier_id TEXT,
    status TEXT DEFAULT 'unverified',
    embedding vector(384),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_fact_type ON fact_records(fact_type);
CREATE INDEX IF NOT EXISTS ix_fact_embedding ON fact_records USING ivfflat (embedding vector_cosine_ops);

-- ---------- L4: Sessions ----------
CREATE TABLE IF NOT EXISTS agent_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agent_name TEXT NOT NULL,
    user_id TEXT,
    referral_id UUID REFERENCES referrals(id),
    state JSONB NOT NULL DEFAULT '{}',
    message_history JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
