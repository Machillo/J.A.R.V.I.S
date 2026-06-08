-- Fase V1 - Corrección estrategia premium: salario fijo, cuotas y plan director.
-- Ejecutar una vez en Supabase antes de recalcular estrategia premium.

-- 1) Salario base mensual fijo del owner. No depende de transacciones bancarias.
INSERT INTO salaries (user_id, amount, source, created_at)
SELECT au.id, 492066, 'Salario base mensual fijo', NOW()
FROM allowed_users au
WHERE au.email = 'gatotico99@gmail.com'
  AND NOT EXISTS (
      SELECT 1
      FROM salaries s
      WHERE s.user_id = au.id
        AND LOWER(s.source) LIKE '%base%'
  );

-- Si ya existía un salario base mensual para el owner, lo dejamos en el valor oficial actual.
UPDATE salaries
SET amount = 492066,
    source = 'Salario base mensual fijo'
WHERE user_id = (SELECT id FROM allowed_users WHERE email = 'gatotico99@gmail.com' LIMIT 1)
  AND LOWER(source) LIKE '%base%';

-- 2) Perfil laboral por hora para poder calcular OT y VGH.
INSERT INTO employment_profile (
    user_id,
    hourly_rate,
    regular_hours_per_week,
    overtime_multiplier,
    holiday_multiplier,
    created_at
)
SELECT au.id, 2277, 47.5, 1.5, 2, NOW()
FROM allowed_users au
WHERE au.email = 'gatotico99@gmail.com'
  AND NOT EXISTS (
      SELECT 1 FROM employment_profile ep
      WHERE ep.user_id = au.id
  );

-- 3) Corrige cuotas importadas sin decimales: ejemplo 6547840 => 65478.40.
UPDATE debts
SET monthly_payment = ROUND(monthly_payment / 100.0, 2)
WHERE user_id = (SELECT id FROM allowed_users WHERE email = 'gatotico99@gmail.com' LIMIT 1)
  AND monthly_payment >= 100000
  AND remaining_amount > 0
  AND monthly_payment > remaining_amount;

-- 4) Corrección específica conocida del Banco Popular si quedó con el monto de planilla mal importado.
UPDATE debts
SET monthly_payment = 65480.40
WHERE user_id = (SELECT id FROM allowed_users WHERE email = 'gatotico99@gmail.com' LIMIT 1)
  AND LOWER(name) LIKE '%popular%'
  AND (monthly_payment > 200000 OR monthly_payment <= 0);

-- 5) Limpia guía premium vieja para que el próximo cálculo use los datos corregidos.
UPDATE ai_premium_guides
SET is_active = FALSE,
    updated_at = NOW()
WHERE user_id = (SELECT id FROM allowed_users WHERE email = 'gatotico99@gmail.com' LIMIT 1)
  AND guide_type = 'financial_strategy'
  AND is_active = TRUE;
