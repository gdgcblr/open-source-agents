-- =============================================================================
-- adk-memshield (v0.1.0) PostgreSQL + pgvector Schema & RLS Policies
-- =============================================================================
-- Production schema. Apply this file only; `02_benchmark_baseline.sql` creates an
-- intentionally unprotected table for benchmarks and must not ship to production.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Create non-superuser role to enforce Row-Level Security (RLS)
--    (PostgreSQL superusers bypass RLS even with FORCE ROW LEVEL SECURITY)
--    'memshield_pass' is a local development default: rotate it in any real deployment.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'memshield_app') THEN
    CREATE ROLE memshield_app LOGIN PASSWORD 'memshield_pass' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO memshield_app;

-- 2. RLS-Protected Semantic Memory Table
--    Identity columns reject empty strings: once a pooled connection has used
--    set_config(..., true), current_setting(..., true) returns '' (not NULL) after the
--    transaction ends, so an empty-string owner would otherwise match a context-free query.
CREATE TABLE IF NOT EXISTS memories (
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

CREATE INDEX IF NOT EXISTS idx_memories_scope_lookup
    ON memories (app_name, tenant_id, user_id);

-- Idempotent session ingestion: ADK may call add_session_to_memory() repeatedly for
-- the same session, so each (owner, session, event) is stored at most once.
CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_session_event
    ON memories (app_name, tenant_id, user_id, session_id, (custom_metadata->>'event_id'))
    WHERE custom_metadata ? 'event_id';

GRANT SELECT, INSERT, UPDATE, DELETE ON memories TO memshield_app;

-- 3. Enable & Force Row-Level Security on `memories`
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE memories FORCE ROW LEVEL SECURITY;

-- Read: own rows, plus tenant-shared rows at or below the agent's clearance.
DROP POLICY IF EXISTS memories_isolation_select ON memories;
CREATE POLICY memories_isolation_select ON memories
    FOR SELECT
    TO memshield_app
    USING (
        app_name = current_setting('app.current_app_name', true)
        AND tenant_id = current_setting('app.current_tenant_id', true)
        AND (
            user_id = current_setting('app.current_user_id', true)
            OR (
                scope = 'tenant_shared'
                AND min_clearance <= COALESCE(NULLIF(current_setting('app.agent_clearance', true), '')::int, 1)
            )
        )
    );

-- Write: own rows only. A tenant_shared row may not be labelled above the writing
-- agent's clearance ("no write-up"), so a Tier-1 agent cannot plant content that
-- higher-clearance agents would trust as executive memory.
DROP POLICY IF EXISTS memories_isolation_insert ON memories;
CREATE POLICY memories_isolation_insert ON memories
    FOR INSERT
    TO memshield_app
    WITH CHECK (
        app_name = current_setting('app.current_app_name', true)
        AND tenant_id = current_setting('app.current_tenant_id', true)
        AND user_id = current_setting('app.current_user_id', true)
        AND (
            scope = 'private'
            OR min_clearance <= COALESCE(NULLIF(current_setting('app.agent_clearance', true), '')::int, 1)
        )
    );

DROP POLICY IF EXISTS memories_isolation_update ON memories;
CREATE POLICY memories_isolation_update ON memories
    FOR UPDATE
    TO memshield_app
    USING (
        app_name = current_setting('app.current_app_name', true)
        AND tenant_id = current_setting('app.current_tenant_id', true)
        AND user_id = current_setting('app.current_user_id', true)
    )
    WITH CHECK (
        app_name = current_setting('app.current_app_name', true)
        AND tenant_id = current_setting('app.current_tenant_id', true)
        AND user_id = current_setting('app.current_user_id', true)
        AND (
            scope = 'private'
            OR min_clearance <= COALESCE(NULLIF(current_setting('app.agent_clearance', true), '')::int, 1)
        )
    );

DROP POLICY IF EXISTS memories_isolation_delete ON memories;
CREATE POLICY memories_isolation_delete ON memories
    FOR DELETE
    TO memshield_app
    USING (
        app_name = current_setting('app.current_app_name', true)
        AND tenant_id = current_setting('app.current_tenant_id', true)
        AND user_id = current_setting('app.current_user_id', true)
    );
