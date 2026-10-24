-- RepoLens PostgreSQL Schema
-- Run as: psql -U repolens -d repolens -f db/schema.sql
-- Idempotent: uses IF NOT EXISTS throughout.

CREATE TABLE IF NOT EXISTS repository_audits (
    id              SERIAL PRIMARY KEY,
    repository_url  TEXT        NOT NULL UNIQUE,
    repository_name TEXT        NOT NULL,
    commit_sha      TEXT,                          -- nullable: captured after clone
    scan_status     TEXT        NOT NULL DEFAULT 'pending',
                                                    -- pending | running | completed | failed
    is_demo         BOOLEAN     NOT NULL DEFAULT FALSE,
    report_json     JSONB,                          -- full normalized findings + AI summary
    report_markdown TEXT,                           -- formatted markdown report
    scanner_status  JSONB,                          -- per-scanner availability and exit codes
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Trigger to auto-update updated_at on every row update.
CREATE OR REPLACE FUNCTION _repolens_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_repolens_updated_at ON repository_audits;
CREATE TRIGGER trg_repolens_updated_at
    BEFORE UPDATE ON repository_audits
    FOR EACH ROW EXECUTE FUNCTION _repolens_set_updated_at();

-- Index for fast URL lookups.
CREATE INDEX IF NOT EXISTS idx_repo_audits_url ON repository_audits (repository_url);
-- Index for sorting by creation time.
CREATE INDEX IF NOT EXISTS idx_repo_audits_created ON repository_audits (created_at DESC);
