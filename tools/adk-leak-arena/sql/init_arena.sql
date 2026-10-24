-- =============================================================================
-- adk-leak-arena (v0.1.0) PostgreSQL + pgvector Arena Schema
-- =============================================================================
-- 1. Loads the production `adk-memshield` RLS-protected `memories` table
-- 2. Creates the baseline `memories_unprotected` table (NO RLS) for side-by-side
--    red-team comparison against application-layer SQL filtering vulnerabilities.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1. Non-superuser role so PostgreSQL Row-Level Security (RLS) is strictly enforced
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'memshield_app') THEN
    CREATE ROLE memshield_app LOGIN PASSWORD 'memshield_pass' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO memshield_app;

-- =============================================================================
-- RIGHT TARGET: `memories` (Kernel-Enforced Row-Level Security via adk-memshield)
-- =============================================================================
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

CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_session_event
    ON memories (app_name, tenant_id, user_id, session_id, (custom_metadata->>'event_id'))
    WHERE custom_metadata ? 'event_id';

GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON memories TO memshield_app;

ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE memories FORCE ROW LEVEL SECURITY;

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

-- =============================================================================
-- LEFT TARGET: `memories_unprotected` (Standard Shared pgvector Table, NO RLS)
-- =============================================================================
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

-- Same per-event idempotency as `memories`, so session ingestion semantics match on both sides.
CREATE UNIQUE INDEX IF NOT EXISTS idx_memories_unprotected_session_event
    ON memories_unprotected (app_name, tenant_id, user_id, session_id, (custom_metadata->>'event_id'))
    WHERE custom_metadata ? 'event_id';

GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON memories_unprotected TO memshield_app;
