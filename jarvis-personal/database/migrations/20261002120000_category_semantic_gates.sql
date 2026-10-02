-- Canonical categories for travel spending, unknown expenses, receivable collections and asset sales.
--
-- The code catalog (backend/finance/category_catalog.py OFFICIAL_CATEGORIES) gains them; this adds the
-- matching rows to category_catalog, which the app reads for its category pickers:
--   - "Viajes y turismo" (expense): flights, lodging, tours. Distinct from the "Viajes" savings goal (AHORRO).
--   - "Sin categoría" (expense): an explicit unknown, so an unrecognised expense never hides in "Compras".
--   - "Cuentas por cobrar" (receivable_payment): a collection of money owed to the user; not income.
--   - "Venta de activo" (asset_sale): cash from selling something the user owned; not income.
-- No existing row is rewritten: rows keep their category; normalize_category maps the names to
-- themselves once deployed.
--
-- Additive and idempotent: one INSERT ... ON CONFLICT DO NOTHING. It never updates, drops or
-- deletes. One transaction: apply it with backend/scripts/apply_migration.py (BACKUP_VERIFIED gate).
--
-- Preflight (read-only): must return zero rows.
--   SELECT 'missing table' WHERE to_regclass('public.category_catalog') IS NULL
--   UNION ALL
--   SELECT 'name used in another group: ' || category_name || ' in ' || group_name FROM category_catalog
--   WHERE (category_name, group_name) IN (('Viajes y turismo', 'AHORRO'), ('Sin categoría', 'GASTOS VARIABLES'),
--                                        ('Cuentas por cobrar', 'INGRESOS'), ('Venta de activo', 'INGRESOS'));
-- Postflight: the query at the end of this file returns zero rows.
-- Rollback (manual, human decision): database/rollback/20261002120000_category_semantic_gates_rollback.sql

BEGIN;

SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '2min';

INSERT INTO public.category_catalog (group_name, category_name, transaction_type, aliases, is_active, sort_order)
VALUES
    ('GASTOS VARIABLES', 'Viajes y turismo', 'expense',
     '["viaje", "viajes", "vuelo", "vuelos", "aerolinea", "aerolínea", "boleto aereo", "boleto aéreo", "hotel", "hospedaje", "alojamiento", "airbnb", "tour", "tours", "turismo"]'::jsonb,
     TRUE, 279),
    ('SIN CLASIFICAR', 'Sin categoría', 'expense', '["sin categoria", "sin categoría", "desconocido", "unknown"]'::jsonb, TRUE, 290),
    ('COBROS Y VENTAS', 'Cuentas por cobrar', 'receivable_payment', '["cuentas por cobrar", "cobro", "cobros"]'::jsonb, TRUE, 450),
    ('COBROS Y VENTAS', 'Venta de activo', 'asset_sale', '["venta de activo", "venta de bien", "venta de vehiculo", "venta de vehículo"]'::jsonb, TRUE, 460)
ON CONFLICT (group_name, category_name) DO NOTHING;

COMMIT;

-- Postflight (read-only): zero rows.
-- SELECT 'missing ' || v.name FROM (VALUES ('Viajes y turismo'), ('Sin categoría'), ('Cuentas por cobrar'), ('Venta de activo')) AS v(name)
-- WHERE NOT EXISTS (SELECT 1 FROM public.category_catalog c WHERE c.category_name = v.name AND c.is_active);
