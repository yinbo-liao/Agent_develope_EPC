-- Auth hardening migration
-- Adds project-level membership (row-level authorization) and supporting indexes.
--
-- Apply after 002_auth_schema.sql:
--   psql -U fpso_user -d fpso_db -f database/migrations/004_auth_hardening.sql

-- Project membership: users may only access projects they belong to.
-- Projects with no rows here are treated as "open to any authenticated user"
-- for backward compatibility (see auth.user_has_project_access).
CREATE TABLE IF NOT EXISTS project_members (
    membership_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    role VARCHAR(50) DEFAULT 'viewer'
        CHECK (role IN ('admin', 'project_manager', 'trade_lead', 'viewer')),
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (project_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_project_members_project ON project_members(project_id);
CREATE INDEX IF NOT EXISTS idx_project_members_user ON project_members(user_id);

-- Refresh-token lookups are always by hash and almost always filtered by the
-- revoked flag; a partial index keeps rotation cheap while tables grow.
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_active
    ON refresh_tokens(token_hash) WHERE revoked = FALSE;

CREATE INDEX IF NOT EXISTS idx_auth_audit_event_type ON auth_audit_log(event_type);
