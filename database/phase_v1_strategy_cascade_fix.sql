-- V1 Strategy Cascade Fix
-- Normaliza perfil laboral y rebajos reales para el usuario owner.
-- Seguro de re-ejecutar.

UPDATE employment_profile
SET hourly_rate = 2390.79,
    regular_hours_per_week = 47.50,
    overtime_multiplier = 1.50,
    holiday_multiplier = 2.00
WHERE user_id = 1;

DELETE FROM payroll_deductions
WHERE user_id = 1;

INSERT INTO payroll_deductions
(user_id, name, deduction_type, amount, frequency)
VALUES
(1, 'CCSS', 'percentage', 10.83, 'monthly'),
(1, 'ASECNX aporte obrero', 'percentage', 5.00, 'monthly'),
(1, 'ASECNX actividades', 'fixed', 250.00, 'monthly'),
(1, 'Préstamo Banco Popular planilla', 'fixed', 16369.60, 'monthly'),
(1, 'Préstamo ASECNX CRC', 'fixed', 2406.50, 'monthly');
