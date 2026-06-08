-- Hotfix V1: salario fijo + cuotas normalizadas + estrategia estable
-- Ejecutar una vez en Supabase SQL Editor.

WITH owner AS (
    SELECT id
    FROM allowed_users
    WHERE lower(email) = 'gatotico99@gmail.com'
    LIMIT 1
)
INSERT INTO salaries (user_id, amount, source, created_at)
SELECT id, 492066.00, 'base_mensual_fija', NOW()
FROM owner
WHERE NOT EXISTS (
    SELECT 1
    FROM salaries s
    WHERE s.user_id = (SELECT id FROM owner)
      AND lower(s.source) IN ('base_mensual_fija', 'salario_base_mensual', 'salario base mensual')
);

WITH owner AS (
    SELECT id
    FROM allowed_users
    WHERE lower(email) = 'gatotico99@gmail.com'
    LIMIT 1
)
UPDATE employment_profile
SET hourly_rate = 2277.00,
    regular_hours_per_week = 47.50,
    overtime_multiplier = 1.50,
    holiday_multiplier = 2.00
WHERE user_id = (SELECT id FROM owner);

WITH owner AS (
    SELECT id
    FROM allowed_users
    WHERE lower(email) = 'gatotico99@gmail.com'
    LIMIT 1
)
INSERT INTO employment_profile (user_id, hourly_rate, regular_hours_per_week, overtime_multiplier, holiday_multiplier, created_at)
SELECT id, 2277.00, 47.50, 1.50, 2.00, NOW()
FROM owner
WHERE NOT EXISTS (
    SELECT 1 FROM employment_profile ep WHERE ep.user_id = (SELECT id FROM owner)
);

-- Rebajo porcentual aplicado a OT y bonos. Cambiable después desde Jarvis/configuración.
WITH owner AS (
    SELECT id
    FROM allowed_users
    WHERE lower(email) = 'gatotico99@gmail.com'
    LIMIT 1
)
INSERT INTO payroll_deductions (user_id, name, deduction_type, amount, frequency, created_at)
SELECT id, 'Rebajo extra planilla', 'percentage', 10.67, 'monthly', NOW()
FROM owner
WHERE NOT EXISTS (
    SELECT 1
    FROM payroll_deductions pd
    WHERE pd.user_id = (SELECT id FROM owner)
      AND pd.deduction_type = 'percentage'
);

-- Normaliza cuotas importadas sin decimales: 6547840 => 65478.40.
UPDATE debts
SET monthly_payment = ROUND(monthly_payment / 100.0, 2)
WHERE monthly_payment >= 1000000
   OR (remaining_amount > 0 AND monthly_payment > remaining_amount AND monthly_payment >= 100000);

-- Mantiene OpenAI en gpt-5-mini para owner.
WITH owner AS (
    SELECT id
    FROM allowed_users
    WHERE lower(email) = 'gatotico99@gmail.com'
    LIMIT 1
)
UPDATE ai_premium_settings
SET model = 'gpt-5-mini',
    monthly_budget_usd = 10.00,
    owner_only = TRUE,
    updated_at = NOW()
WHERE user_id = (SELECT id FROM owner);
