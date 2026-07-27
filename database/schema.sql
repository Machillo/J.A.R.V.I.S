CREATE TABLE IF NOT EXISTS allowed_users (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL DEFAULT 'user',
    status TEXT NOT NULL DEFAULT 'pending',
    supabase_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    allowed_user_id BIGINT REFERENCES allowed_users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    country TEXT NOT NULL,
    timezone TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS settings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT REFERENCES allowed_users(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    UNIQUE(user_id, key)
);

CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    title TEXT NOT NULL,
    description TEXT,
    event_type TEXT NOT NULL,
    event_date TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    action TEXT NOT NULL,
    detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS salaries (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    amount NUMERIC(14, 2) NOT NULL,
    source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bonuses (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    amount NUMERIC(14, 2) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS debts (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    name TEXT NOT NULL,
    debt_type TEXT NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL,
    remaining_amount NUMERIC(14, 2) NOT NULL,
    monthly_payment NUMERIC(14, 2) NOT NULL,
    interest_rate NUMERIC(8, 4),
    term_months INTEGER,
    payment_day INTEGER,
    start_date DATE,
    first_payment_date DATE,
    auto_update_monthly BOOLEAN NOT NULL DEFAULT TRUE,
    installments_paid INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS debt_payments (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    debt_id BIGINT NOT NULL REFERENCES debts(id) ON DELETE CASCADE,
    payment_type TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    previous_remaining_amount NUMERIC(14, 2) NOT NULL,
    new_remaining_amount NUMERIC(14, 2) NOT NULL,
    previous_monthly_payment NUMERIC(14, 2) NOT NULL,
    new_monthly_payment NUMERIC(14, 2) NOT NULL,
    principal_amount NUMERIC(14, 2),
    interest_amount NUMERIC(14, 2),
    description TEXT,
    payment_date DATE,
    installment_number INTEGER,
    source TEXT NOT NULL DEFAULT 'manual',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS savings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    name TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS investments (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    name TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS expenses (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    category TEXT NOT NULL,
    expense_type TEXT NOT NULL,
    description TEXT,
    amount NUMERIC(14, 2) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS employment_profile (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    hourly_rate NUMERIC(14, 2) NOT NULL,
    regular_hours_per_week NUMERIC(8, 2) NOT NULL,
    overtime_multiplier NUMERIC(8, 4) NOT NULL,
    holiday_multiplier NUMERIC(8, 4) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payroll_deductions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    name TEXT NOT NULL,
    deduction_type TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    frequency TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payroll_events (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    event_type TEXT NOT NULL,
    hours NUMERIC(8, 2) NOT NULL,
    multiplier NUMERIC(8, 4) NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS financial_goals (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    name TEXT NOT NULL,
    target_amount NUMERIC(14, 2) NOT NULL,
    current_amount NUMERIC(14, 2) NOT NULL DEFAULT 0,
    target_date TEXT,
    priority TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payment_schedules (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    name TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id BIGINT,
    payment_method TEXT NOT NULL,
    frequency TEXT NOT NULL,
    day_of_month INTEGER,
    cut_day INTEGER,
    payment_day INTEGER,
    auto_deducted BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pay_schedule (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    pay_frequency TEXT NOT NULL,
    pay_day TEXT,
    first_pay_date TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS credit_card_settings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    name TEXT NOT NULL DEFAULT 'BAC tarjetas',
    cut_day INTEGER NOT NULL DEFAULT 21,
    payment_day INTEGER NOT NULL DEFAULT 5,
    bank TEXT NOT NULL DEFAULT 'bac',
    card_last4 TEXT,
    owner_label TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_credit_card_settings_user_bank_card
ON credit_card_settings(user_id, bank, card_last4);

CREATE TABLE IF NOT EXISTS transactions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    transaction_date TEXT NOT NULL,
    description TEXT NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    transaction_type TEXT NOT NULL,
    category TEXT NOT NULL,
    account TEXT,
    source TEXT,
    notes TEXT,
    original_amount NUMERIC(14, 2),
    original_currency TEXT,
    exchange_rate NUMERIC(14, 6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_allowed_users_email ON allowed_users(email);
CREATE INDEX IF NOT EXISTS idx_allowed_users_supabase_user_id ON allowed_users(supabase_user_id);

CREATE INDEX IF NOT EXISTS idx_events_user_id ON events(user_id);
CREATE INDEX IF NOT EXISTS idx_logs_user_id ON logs(user_id);
CREATE INDEX IF NOT EXISTS idx_salaries_user_id ON salaries(user_id);
CREATE INDEX IF NOT EXISTS idx_bonuses_user_id ON bonuses(user_id);
CREATE INDEX IF NOT EXISTS idx_debts_user_id ON debts(user_id);
CREATE INDEX IF NOT EXISTS idx_debt_payments_user_id ON debt_payments(user_id);
CREATE INDEX IF NOT EXISTS idx_debt_payments_debt_id ON debt_payments(debt_id);
CREATE INDEX IF NOT EXISTS idx_savings_user_id ON savings(user_id);
CREATE INDEX IF NOT EXISTS idx_investments_user_id ON investments(user_id);
CREATE INDEX IF NOT EXISTS idx_expenses_user_id ON expenses(user_id);
CREATE INDEX IF NOT EXISTS idx_employment_profile_user_id ON employment_profile(user_id);
CREATE INDEX IF NOT EXISTS idx_payroll_deductions_user_id ON payroll_deductions(user_id);
CREATE INDEX IF NOT EXISTS idx_payroll_events_user_id ON payroll_events(user_id);
CREATE INDEX IF NOT EXISTS idx_financial_goals_user_id ON financial_goals(user_id);
CREATE INDEX IF NOT EXISTS idx_payment_schedules_user_id ON payment_schedules(user_id);
CREATE INDEX IF NOT EXISTS idx_pay_schedule_user_id ON pay_schedule(user_id);
CREATE INDEX IF NOT EXISTS idx_credit_card_settings_user_id ON credit_card_settings(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(transaction_date);


CREATE TABLE IF NOT EXISTS receivables (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    person_name TEXT NOT NULL,
    original_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
    paid_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
    pending_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    notes TEXT,
    source_type TEXT NOT NULL DEFAULT 'manual',
    source_key TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS receivable_payments (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    receivable_id BIGINT NOT NULL REFERENCES receivables(id) ON DELETE CASCADE,
    amount NUMERIC(14,2) NOT NULL,
    source_transaction_id BIGINT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_receivables_user_status ON receivables(user_id, status);
CREATE INDEX IF NOT EXISTS idx_receivables_source_key ON receivables(user_id, source_key);
CREATE INDEX IF NOT EXISTS idx_receivable_payments_receivable ON receivable_payments(user_id, receivable_id);

CREATE TABLE IF NOT EXISTS receivable_entries (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    receivable_id BIGINT NOT NULL REFERENCES receivables(id) ON DELETE CASCADE,
    entry_type TEXT NOT NULL,
    amount NUMERIC(14,2) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    entry_date DATE NOT NULL DEFAULT CURRENT_DATE,
    source_type TEXT NOT NULL DEFAULT 'manual',
    source_key TEXT,
    source_transaction_id BIGINT,
    cycle_start DATE,
    cycle_end DATE,
    is_archived BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_receivable_entries_account ON receivable_entries(user_id, receivable_id, entry_date DESC, id DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_receivable_entries_source_key ON receivable_entries(user_id, source_key) WHERE source_key IS NOT NULL;


CREATE TABLE IF NOT EXISTS category_catalog (
    id BIGSERIAL PRIMARY KEY,
    group_name TEXT NOT NULL,
    category_name TEXT NOT NULL,
    transaction_type TEXT NOT NULL,
    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(group_name, category_name)
);

CREATE INDEX IF NOT EXISTS idx_category_catalog_group ON category_catalog(group_name);
CREATE INDEX IF NOT EXISTS idx_category_catalog_active ON category_catalog(is_active);

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

-- Phase 2: persistent memory per user
CREATE TABLE IF NOT EXISTS memory_items (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES allowed_users(id) ON DELETE CASCADE,
    category TEXT NOT NULL DEFAULT 'other',
    title TEXT,
    content TEXT NOT NULL,
    importance INTEGER NOT NULL DEFAULT 3,
    source TEXT NOT NULL DEFAULT 'manual',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memory_items_user_active ON memory_items(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_memory_items_category ON memory_items(category);

CREATE TABLE IF NOT EXISTS user_preferences (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES allowed_users(id) ON DELETE CASCADE,
    preference_key TEXT NOT NULL,
    preference_value JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, preference_key)
);

-- Phase 5: fixed expenses and recurring payment control
CREATE TABLE IF NOT EXISTS fixed_expenses (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES allowed_users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Gastos fijos',
    expected_amount NUMERIC(14, 2),
    currency TEXT NOT NULL DEFAULT 'CRC',
    frequency TEXT NOT NULL DEFAULT 'monthly',
    interval_months INTEGER NOT NULL DEFAULT 1,
    start_month TEXT,
    due_day INTEGER,
    reminder_days INTEGER NOT NULL DEFAULT 3,
    payment_method TEXT NOT NULL DEFAULT 'manual',
    auto_deducted BOOLEAN NOT NULL DEFAULT FALSE,
    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
    notes TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, name)
);

CREATE TABLE IF NOT EXISTS fixed_expense_matches (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES allowed_users(id) ON DELETE CASCADE,
    fixed_expense_id BIGINT NOT NULL REFERENCES fixed_expenses(id) ON DELETE CASCADE,
    transaction_id BIGINT REFERENCES transactions(id) ON DELETE SET NULL,
    period_month TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    confidence NUMERIC(5, 2) NOT NULL DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, fixed_expense_id, period_month)
);

CREATE INDEX IF NOT EXISTS idx_fixed_expenses_user_id ON fixed_expenses(user_id);
CREATE INDEX IF NOT EXISTS idx_fixed_expenses_active ON fixed_expenses(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_fixed_expense_matches_user_period ON fixed_expense_matches(user_id, period_month);



-- Fase 6 — Correos 24/7 / Email Monitor
-- Ejecutar en Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS email_monitor_settings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    auto_commit_confidence NUMERIC NOT NULL DEFAULT 0.90,
    monitored_senders TEXT[] NOT NULL DEFAULT ARRAY['bac','credomatic','popular','multimoney'],
    gmail_query TEXT NOT NULL DEFAULT '',
    last_scan_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS email_ingested_messages (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL DEFAULT 'gmail',
    provider_message_id TEXT,
    fingerprint TEXT NOT NULL,
    sender TEXT,
    subject TEXT,
    received_at TIMESTAMPTZ,
    bank TEXT,
    status TEXT NOT NULL DEFAULT 'processed',
    raw_excerpt TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, fingerprint),
    UNIQUE(user_id, provider, provider_message_id)
);

CREATE TABLE IF NOT EXISTS email_transaction_candidates (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email_message_id BIGINT REFERENCES email_ingested_messages(id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL,
    transaction_id BIGINT REFERENCES transactions(id) ON DELETE SET NULL,
    transaction_date DATE NOT NULL,
    description TEXT NOT NULL,
    amount NUMERIC NOT NULL,
    transaction_type TEXT NOT NULL,
    category TEXT NOT NULL,
    account TEXT DEFAULT '',
    source TEXT NOT NULL DEFAULT 'email_monitor',
    notes TEXT DEFAULT '',
    original_amount NUMERIC,
    original_currency TEXT,
    exchange_rate NUMERIC,
    confidence NUMERIC NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'pending',
    review_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, fingerprint)
);

CREATE INDEX IF NOT EXISTS idx_email_candidates_user_status
ON email_transaction_candidates(user_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_email_messages_user_created
ON email_ingested_messages(user_id, created_at DESC);

INSERT INTO email_monitor_settings (user_id, gmail_query)
SELECT id,
       '(from:notificacion@notificacionesbaccr.com OR from:notificaciones@baccredomatic.cr OR from:estadosdecuenta@baccredomatic.cr OR from:estadodecuenta@baccredomatic.cr OR from:multimoneycr@multimoney.com OR from:financiera@multimoney.com OR from:bancopopular OR from:popular OR "BAC - SINPE" OR "Banco Popular") ("Notificación de transacción" OR "Notificación de Transferencia" OR "Transacción realizada" OR "Estado de cuenta" OR "Estado de Cuenta" OR "estados de cuenta" OR SINPE OR transferencia OR compra OR pago OR depósito OR deposito OR retiro OR abono)'
FROM users
WHERE email = 'gatotico99@gmail.com'
ON CONFLICT (user_id)
DO UPDATE SET gmail_query = EXCLUDED.gmail_query, updated_at = NOW();

-- Email statement documents for reconciliation, not direct expenses
CREATE TABLE IF NOT EXISTS email_statement_documents (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    email_message_id BIGINT REFERENCES email_ingested_messages(id) ON DELETE CASCADE,
    bank TEXT NOT NULL,
    subject TEXT,
    statement_month TEXT,
    received_at TIMESTAMPTZ,
    attachment_names TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    extracted_text_excerpt TEXT,
    status TEXT NOT NULL DEFAULT 'pending_reconciliation',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, email_message_id)
);


-- Fase 7 — Notificaciones reales Web Push / PWA
-- Ejecutar en Supabase SQL Editor.

CREATE TABLE IF NOT EXISTS notification_subscriptions (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES allowed_users(id) ON DELETE CASCADE,
    channel TEXT NOT NULL DEFAULT 'browser',
    endpoint TEXT,
    payload JSONB,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_success_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, channel, endpoint)
);

ALTER TABLE notification_subscriptions ADD COLUMN IF NOT EXISTS last_success_at TIMESTAMPTZ;
ALTER TABLE notification_subscriptions ADD COLUMN IF NOT EXISTS last_error TEXT;

CREATE TABLE IF NOT EXISTS notification_jobs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES allowed_users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'general',
    scheduled_at TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    reference_type TEXT,
    reference_id TEXT,
    dedupe_key TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    sent_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, dedupe_key)
);

CREATE INDEX IF NOT EXISTS idx_notification_jobs_due ON notification_jobs(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_notification_jobs_user ON notification_jobs(user_id, scheduled_at);

-- Ejemplo opcional para prueba manual. Cambiá scheduled_at si querés probar cron.
-- INSERT INTO notification_jobs (user_id, title, body, category, scheduled_at, dedupe_key)
-- SELECT id, 'J.A.R.V.I.S.', 'Señor Kenneth, prueba programada de notificaciones.', 'test', NOW() + INTERVAL '1 minute', 'manual:test:phase7'
-- FROM allowed_users WHERE email = 'gatotico99@gmail.com'
-- ON CONFLICT (user_id, dedupe_key) DO NOTHING;


-- V1 Premium Strategy / Additional cards support
CREATE TABLE IF NOT EXISTS card_aliases (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    card_last4 TEXT NOT NULL,
    owner_label TEXT NOT NULL,
    relationship TEXT,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, card_last4)
);
CREATE INDEX IF NOT EXISTS idx_card_aliases_user ON card_aliases(user_id);

-- Email parser Fase 1 hardening: audit, card cycle and dedupe metadata
ALTER TABLE email_ingested_messages ADD COLUMN IF NOT EXISTS raw_body TEXT;
ALTER TABLE email_ingested_messages ADD COLUMN IF NOT EXISTS body_text TEXT;
ALTER TABLE email_ingested_messages ADD COLUMN IF NOT EXISTS attachment_names TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[];
ALTER TABLE email_ingested_messages ADD COLUMN IF NOT EXISTS attachment_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE email_ingested_messages ADD COLUMN IF NOT EXISTS parse_reason TEXT;

ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS card_last4 TEXT;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS card_owner TEXT;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS billing_cycle_start DATE;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS billing_cycle_end DATE;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS dedupe_key TEXT;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS duplicate_of BIGINT;

CREATE INDEX IF NOT EXISTS idx_email_candidates_card_cycle
ON email_transaction_candidates(user_id, card_last4, billing_cycle_start, billing_cycle_end);

CREATE INDEX IF NOT EXISTS idx_email_candidates_dedupe
ON email_transaction_candidates(user_id, transaction_date, amount, transaction_type, status);

CREATE TABLE IF NOT EXISTS card_aliases (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    card_last4 TEXT NOT NULL,
    owner_label TEXT NOT NULL,
    relationship TEXT,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, card_last4)
);

CREATE TABLE IF NOT EXISTS credit_card_settings (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL DEFAULT 1,
    name TEXT NOT NULL DEFAULT 'BAC tarjetas',
    bank TEXT NOT NULL DEFAULT 'bac',
    card_last4 TEXT,
    owner_label TEXT,
    cut_day INTEGER NOT NULL DEFAULT 21,
    payment_day INTEGER NOT NULL DEFAULT 5,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_credit_card_settings_user_bank_card
ON credit_card_settings(user_id, bank, card_last4);

CREATE TABLE IF NOT EXISTS email_parser_logs (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    email_message_id BIGINT,
    provider_message_id TEXT,
    sender TEXT,
    subject TEXT,
    bank TEXT,
    action TEXT NOT NULL,
    result TEXT,
    reason TEXT,
    extracted_payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE email_parser_logs ADD COLUMN IF NOT EXISTS email_message_id BIGINT;
ALTER TABLE email_parser_logs ADD COLUMN IF NOT EXISTS result TEXT;
ALTER TABLE email_parser_logs ADD COLUMN IF NOT EXISTS extracted_payload JSONB;

-- Email parser Fase 1.5: merchant normalization + semantic canonical dedupe
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS canonical_transaction_id BIGINT;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS transaction_time TIME;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS raw_description TEXT;
ALTER TABLE email_transaction_candidates ADD COLUMN IF NOT EXISTS normalized_description TEXT;

CREATE INDEX IF NOT EXISTS idx_email_candidates_semantic_dedupe
ON email_transaction_candidates(user_id, transaction_date, amount, transaction_time, status);

CREATE INDEX IF NOT EXISTS idx_email_candidates_canonical
ON email_transaction_candidates(user_id, canonical_transaction_id);

-- Email parser duplicate traceability hardening
CREATE INDEX IF NOT EXISTS idx_email_candidates_canonical
ON email_transaction_candidates(user_id, canonical_transaction_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_email_candidate_duplicate_trace'
    ) THEN
        ALTER TABLE email_transaction_candidates
        ADD CONSTRAINT chk_email_candidate_duplicate_trace
        CHECK (
            status <> 'duplicate'
            OR canonical_transaction_id IS NOT NULL
            OR transaction_id IS NOT NULL
        ) NOT VALID;
    END IF;
END $$;

-- Fase Correos 100%: review flow indexes + known card aliases are also enforced by backend/migration.
CREATE INDEX IF NOT EXISTS idx_email_candidates_user_status_created
ON email_transaction_candidates(user_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_email_candidates_transaction_id
ON email_transaction_candidates(user_id, transaction_id);

CREATE INDEX IF NOT EXISTS idx_email_messages_provider_message
ON email_ingested_messages(user_id, provider, provider_message_id);


CREATE UNIQUE INDEX IF NOT EXISTS idx_debt_payments_unique_monthly_due
ON debt_payments(user_id, debt_id, payment_date)
WHERE payment_type = 'monthly_payment' AND payment_date IS NOT NULL;
