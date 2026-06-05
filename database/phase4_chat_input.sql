CREATE TABLE IF NOT EXISTS chat_sessions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES allowed_users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_pending_actions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES allowed_users(id) ON DELETE CASCADE,
    session_id BIGINT REFERENCES chat_sessions(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    current_field TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    missing_fields JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_pending_actions_user_id ON chat_pending_actions(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_pending_actions_status ON chat_pending_actions(status);
