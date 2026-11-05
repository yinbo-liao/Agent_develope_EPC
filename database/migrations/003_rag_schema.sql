-- =============================================================================
-- FPSO EPC Project Control System — Migration 003: RAG AI Schema
-- Adds: AI conversation sessions, messages, tool audit log, insight cache
-- Run: psql -U fpso_user -d fpso_db -f database/migrations/003_rag_schema.sql
-- =============================================================================

BEGIN;

-- AI conversation sessions (per project, per user)
CREATE TABLE IF NOT EXISTS ai_sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
    title VARCHAR(200),
    model_used VARCHAR(50) DEFAULT 'rule_based',  -- deepseek, claude, rule_based
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_sessions_project ON ai_sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_ai_sessions_user ON ai_sessions(user_id);

-- AI messages (chat history with tool calls)
CREATE TABLE IF NOT EXISTS ai_messages (
    message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES ai_sessions(session_id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,  -- user, assistant, tool, system
    content TEXT,
    tool_calls JSONB,           -- [{name, args, result}]
    token_count INTEGER,
    model VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_messages_session ON ai_messages(session_id);

-- AI tool execution audit log
CREATE TABLE IF NOT EXISTS ai_tool_audit (
    audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id) ON DELETE SET NULL,
    session_id UUID REFERENCES ai_sessions(session_id) ON DELETE SET NULL,
    tool_name VARCHAR(100) NOT NULL,
    tool_input JSONB,
    tool_output JSONB,
    execution_time_ms INTEGER,
    error TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_tool_audit_project ON ai_tool_audit(project_id);
CREATE INDEX IF NOT EXISTS idx_ai_tool_audit_tool ON ai_tool_audit(tool_name, created_at DESC);

-- AI insight cache (pre-computed insights per project)
CREATE TABLE IF NOT EXISTS ai_insights (
    insight_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(project_id) ON DELETE CASCADE,
    insight_type VARCHAR(50) NOT NULL,  -- schedule_risk, conflict, gate_assessment, kpi_summary, report
    payload JSONB NOT NULL,
    confidence DECIMAL(3,2),
    generated_by VARCHAR(20) DEFAULT 'rule_based',  -- deepseek, claude, rule_based
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_insights_project_type ON ai_insights(project_id, insight_type, created_at DESC);

-- Update ai_sessions.updated_at on message insert
CREATE OR REPLACE FUNCTION update_ai_session_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE ai_sessions SET updated_at = NOW() WHERE session_id = NEW.session_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_ai_message_timestamp ON ai_messages;
CREATE TRIGGER trg_ai_message_timestamp
    AFTER INSERT ON ai_messages
    FOR EACH ROW EXECUTE FUNCTION update_ai_session_timestamp();

COMMIT;
