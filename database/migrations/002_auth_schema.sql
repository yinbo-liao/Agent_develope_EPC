-- Auth & RBAC schema for FPSO EPC Project Control System
-- Phase 2: OAuth2+JWT authentication with role-based access control

-- Users table
CREATE TABLE IF NOT EXISTS users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(100) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name VARCHAR(200),
    role VARCHAR(50) NOT NULL DEFAULT 'viewer'
        CHECK (role IN ('admin', 'project_manager', 'trade_lead', 'viewer')),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    last_login TIMESTAMP
);

-- Refresh token table (for token rotation / revocation)
CREATE TABLE IF NOT EXISTS refresh_tokens (
    token_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(user_id) ON DELETE CASCADE,
    token_hash VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    revoked BOOLEAN DEFAULT FALSE
);

-- Audit log for authentication events
CREATE TABLE IF NOT EXISTS auth_audit_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(user_id),
    event_type VARCHAR(50) NOT NULL,  -- LOGIN, LOGOUT, TOKEN_REFRESH, FAILED_LOGIN
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_audit_user ON auth_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_audit_created ON auth_audit_log(created_at);

-- No default admin is seeded here on purpose: shipping a known password hash is
-- a credential exposure. On startup the application creates the first admin
-- from FPSO_BOOTSTRAP_ADMIN_USERNAME / FPSO_BOOTSTRAP_ADMIN_PASSWORD when the
-- users table is empty (see auth.bootstrap_admin). Production refuses to start
-- with an empty users table and no bootstrap password.
--
-- To create an admin manually instead:
--   python -c "from auth import hash_password; print(hash_password('use-a-long-random-password'))"
--   INSERT INTO users (username, email, hashed_password, role)
--   VALUES ('admin', 'admin@example.com', '<hash>', 'admin');
