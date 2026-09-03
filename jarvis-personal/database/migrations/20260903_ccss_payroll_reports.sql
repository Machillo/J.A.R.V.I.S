CREATE TABLE IF NOT EXISTS payroll_salary_reports (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    workspace_id UUID NOT NULL,
    email_message_id BIGINT REFERENCES email_ingested_messages(id) ON DELETE SET NULL,
    provider_message_id TEXT,
    period_month TEXT NOT NULL,
    reported_salary NUMERIC NOT NULL,
    trans_previous_salary NUMERIC,
    previous_salary NUMERIC,
    daily_subsidy NUMERIC,
    employer_number TEXT,
    verification_code TEXT,
    source TEXT NOT NULL DEFAULT 'ccss_order_patronal',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(workspace_id, period_month),
    UNIQUE(workspace_id, provider_message_id)
);

CREATE INDEX IF NOT EXISTS idx_payroll_salary_reports_period
ON payroll_salary_reports(workspace_id, period_month);
