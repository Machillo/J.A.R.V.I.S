-- V1 Director final fix: avoid double counting payroll Popular and debt-like fixed expenses.
-- Ejecutar una vez en Supabase.

-- El Banco Popular queda como deuda, no como rebajo de planilla.
DELETE FROM payroll_deductions
WHERE user_id = 1
  AND LOWER(name) LIKE '%popular%';

-- Mantener salario/hora correcto.
UPDATE employment_profile
SET hourly_rate = 2390.79,
    regular_hours_per_week = 47.50
WHERE user_id = 1;

-- Marcar explícitamente gastos fijos que son deudas para recordatorios, pero la estrategia no los resta como vida.
UPDATE fixed_expenses
SET auto_deducted = FALSE
WHERE user_id = 1
  AND LOWER(name) IN ('préstamo popular', 'prestamo popular');
