
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


-- Default fixed expenses for Kenneth / owner user. Safe to run multiple times.
INSERT INTO fixed_expenses
(user_id, name, category, expected_amount, currency, frequency, interval_months, start_month, due_day, reminder_days, payment_method, auto_deducted, aliases, notes, is_active)
VALUES
(1,'Casa','Vivienda',100000,'CRC','monthly',1,NULL,30,3,'manual',FALSE,'["casa y prestamo","casa"]'::jsonb,'Aporte mensual a casa.',TRUE),
(1,'Préstamo papá','Familiar',30387.13,'CRC','monthly',1,NULL,30,3,'manual',FALSE,'["prestamo papa","préstamo papá","casa y prestamo"]'::jsonb,'Parte de Casa y Préstamo.',TRUE),
(1,'Nutricionista','Salud',40000,'CRC','monthly',2,'2026-02',14,3,'manual',FALSE,'["nutricionista"]'::jsonb,'Cada 2 meses.',TRUE),
(1,'Préstamo Popular','Banco Popular',65480.40,'CRC','monthly',1,NULL,NULL,3,'planilla',TRUE,'["popular","prestamo popular","banco popular"]'::jsonb,'Rebajo directo de planilla.',TRUE),
(1,'Línea Liberty','Teléfono',33850.86,'CRC','monthly',1,NULL,4,3,'manual',FALSE,'["liberty","linea","línea","pago liberty"]'::jsonb,'Pago de línea Liberty.',TRUE),
(1,'Gimnasio','Salud',24950,'CRC','monthly',1,NULL,4,3,'manual',FALSE,'["novo fit","gimnasio","gym"]'::jsonb,'Membresía gimnasio.',TRUE),
(1,'Préstamo BAC','Tarjeta BAC',16950,'CRC','monthly',1,NULL,NULL,3,'manual',FALSE,'["prestamo bac","préstamo bac"]'::jsonb,'Préstamo BAC.',TRUE),
(1,'Reloj','Reloj',7793.30,'CRC','monthly',1,NULL,22,3,'tarjeta',FALSE,'["ishop","reloj","tasa cero"]'::jsonb,'Cuota tasa cero reloj.',TRUE),
(1,'Minicuota','Tarjeta BAC',8760,'CRC','monthly',1,NULL,22,3,'tarjeta',FALSE,'["minicuotas","minicuota","credomatic minic"]'::jsonb,'Minicuota BAC.',TRUE),
(1,'PS Plus','Videojuegos',7000,'CRC','monthly',1,NULL,16,3,'tarjeta',FALSE,'["playstation","ps plus","playstation network"]'::jsonb,'Monto estimado; Jarvis ajusta contra transacciones.',TRUE),
(1,'Seguro tarjeta','Seguros',2950,'CRC','monthly',1,NULL,21,3,'tarjeta',FALSE,'["seguro proteccion","seguro protección","bdpc5"]'::jsonb,'Seguro de tarjeta.',TRUE),
(1,'Crunchyroll','Suscripciones',3390,'CRC','monthly',1,NULL,8,3,'tarjeta',FALSE,'["crunchyroll"]'::jsonb,'Streaming.',TRUE),
(1,'Google One','Suscripciones',5537,'CRC','monthly',1,NULL,22,3,'tarjeta',FALSE,'["google one"]'::jsonb,'Suscripción Google One.',TRUE),
(1,'iCloud / Apple','Suscripciones',NULL,'CRC','monthly',1,NULL,NULL,3,'tarjeta',FALSE,'["apple.com","icloud","apple"]'::jsonb,'Monto variable; Jarvis debe aprenderlo con transacciones.',TRUE)
ON CONFLICT (user_id, name)
DO UPDATE SET
    category = EXCLUDED.category,
    expected_amount = EXCLUDED.expected_amount,
    currency = EXCLUDED.currency,
    frequency = EXCLUDED.frequency,
    interval_months = EXCLUDED.interval_months,
    start_month = EXCLUDED.start_month,
    due_day = EXCLUDED.due_day,
    reminder_days = EXCLUDED.reminder_days,
    payment_method = EXCLUDED.payment_method,
    auto_deducted = EXCLUDED.auto_deducted,
    aliases = EXCLUDED.aliases,
    notes = EXCLUDED.notes,
    is_active = TRUE,
    updated_at = NOW();
