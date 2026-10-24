-- =============================================================================
-- adk-memshield (v0.1.0) Benchmark-Only Baseline Table (NO Row-Level Security)
-- =============================================================================
-- Used by tests/ and benchmarks/ to compare an ordinary pgvector table against the
-- RLS-protected `memories` table. Do NOT apply this file in production: it grants the
-- application role full access to a table with no isolation at all.

CREATE TABLE IF NOT EXISTS memories_unprotected (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    app_name TEXT NOT NULL CHECK (app_name <> ''),
    tenant_id TEXT NOT NULL CHECK (tenant_id <> ''),
    user_id TEXT NOT NULL CHECK (user_id <> ''),
    session_id TEXT,
    author TEXT DEFAULT 'user',
    scope TEXT NOT NULL DEFAULT 'private' CHECK (scope IN ('private', 'tenant_shared')),
    min_clearance INTEGER NOT NULL DEFAULT 1 CHECK (min_clearance BETWEEN 1 AND 5),
    content TEXT NOT NULL,
    custom_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding vector(384) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memories_unprotected_scope_lookup
    ON memories_unprotected (app_name, tenant_id, user_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_unprotected_session_event
    ON memories_unprotected (app_name, tenant_id, user_id, session_id, (custom_metadata->>'event_id'))
    WHERE custom_metadata ? 'event_id';

GRANT SELECT, INSERT, UPDATE, DELETE ON memories_unprotected TO memshield_app;
