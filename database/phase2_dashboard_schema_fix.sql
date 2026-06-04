ALTER TABLE allowed_users ADD COLUMN IF NOT EXISTS supabase_user_id TEXT;
ALTER TABLE allowed_users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;
ALTER TABLE allowed_users ADD COLUMN IF NOT EXISTS role TEXT DEFAULT 'user';
ALTER TABLE allowed_users ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active';

UPDATE allowed_users SET role = 'user' WHERE role IS NULL;
UPDATE allowed_users SET status = 'active' WHERE status IS NULL;

ALTER TABLE salaries ADD COLUMN IF NOT EXISTS user_id BIGINT;
ALTER TABLE bonuses ADD COLUMN IF NOT EXISTS user_id BIGINT;
ALTER TABLE employment_profile ADD COLUMN IF NOT EXISTS user_id BIGINT;
ALTER TABLE payroll_deductions ADD COLUMN IF NOT EXISTS user_id BIGINT;
ALTER TABLE payroll_events ADD COLUMN IF NOT EXISTS user_id BIGINT;
ALTER TABLE payment_schedules ADD COLUMN IF NOT EXISTS user_id BIGINT;
ALTER TABLE pay_schedule ADD COLUMN IF NOT EXISTS user_id BIGINT;
ALTER TABLE credit_card_settings ADD COLUMN IF NOT EXISTS user_id BIGINT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS user_id BIGINT;
ALTER TABLE logs ADD COLUMN IF NOT EXISTS user_id BIGINT;

CREATE INDEX IF NOT EXISTS idx_allowed_users_email ON allowed_users(email);
CREATE INDEX IF NOT EXISTS idx_allowed_users_supabase_user_id ON allowed_users(supabase_user_id);
CREATE INDEX IF NOT EXISTS idx_salaries_user_id ON salaries(user_id);
CREATE INDEX IF NOT EXISTS idx_bonuses_user_id ON bonuses(user_id);
CREATE INDEX IF NOT EXISTS idx_employment_profile_user_id ON employment_profile(user_id);
CREATE INDEX IF NOT EXISTS idx_payroll_deductions_user_id ON payroll_deductions(user_id);
CREATE INDEX IF NOT EXISTS idx_payroll_events_user_id ON payroll_events(user_id);
CREATE INDEX IF NOT EXISTS idx_payment_schedules_user_id ON payment_schedules(user_id);
CREATE INDEX IF NOT EXISTS idx_pay_schedule_user_id ON pay_schedule(user_id);
CREATE INDEX IF NOT EXISTS idx_credit_card_settings_user_id ON credit_card_settings(user_id);
CREATE INDEX IF NOT EXISTS idx_events_user_id ON events(user_id);
CREATE INDEX IF NOT EXISTS idx_logs_user_id ON logs(user_id);

INSERT INTO allowed_users (email, role, status, created_at)
VALUES ('gatotico99@gmail.com', 'owner', 'active', NOW())
ON CONFLICT (email)
DO UPDATE SET role = 'owner', status = 'active';
