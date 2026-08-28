-- JARVIS Users: personal plan foundation (Free / Basic / VIP).
-- Run once in the JARVIS Users Supabase project only.

ALTER TABLE profiles
    ADD COLUMN IF NOT EXISTS plan_selected BOOLEAN NOT NULL DEFAULT FALSE;

INSERT INTO plans (code, name, is_active)
VALUES
    ('free', 'Gratis', TRUE),
    ('basic', 'Basic', TRUE),
    ('vip', 'VIP', TRUE)
ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, is_active=TRUE;

-- Keep the old premium row inactive instead of deleting history that may reference it.
UPDATE plans SET is_active=FALSE WHERE code='premium';

INSERT INTO features (code, description) VALUES
    ('finance_overview', 'Resumen financiero'),
    ('spending', 'Ingresos y gastos'),
    ('debts', 'Registro y seguimiento de deudas'),
    ('goals', 'Metas financieras'),
    ('transactions', 'Transacciones'),
    ('overtime', 'Horas extra'),
    ('strategy_basic', 'Estrategia financiera determinística básica'),
    ('strategy_vip', 'Dirección financiera dinámica VIP'),
    ('projections', 'Proyecciones y escenarios financieros'),
    ('smart_goals', 'Metas coordinadas con la estrategia financiera')
ON CONFLICT (code) DO UPDATE SET description=EXCLUDED.description;

-- Rebuild personal-plan feature assignments so access is data-driven.
DELETE FROM plan_features
WHERE plan_id IN (SELECT id FROM plans WHERE code IN ('free','basic','vip'));

INSERT INTO plan_features (plan_id, feature_id, enabled)
SELECT p.id, f.id, TRUE
FROM plans p
JOIN features f ON (
    (p.code='free' AND f.code IN ('finance_overview','spending','debts','goals','transactions','overtime'))
    OR
    (p.code='basic' AND f.code IN ('finance_overview','spending','debts','goals','transactions','overtime','strategy_basic'))
    OR
    (p.code='vip' AND f.code IN ('finance_overview','spending','debts','goals','transactions','overtime','strategy_basic','strategy_vip','projections','smart_goals'))
)
WHERE p.code IN ('free','basic','vip')
ON CONFLICT (plan_id, feature_id) DO UPDATE SET enabled=TRUE;

-- Existing accounts must explicitly choose a plan next time they enter.
-- Their financial data and completed onboarding are intentionally preserved.
UPDATE profiles SET plan_selected=FALSE;
