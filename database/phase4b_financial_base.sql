-- Fase 4B: configuración financiera base de J.A.R.V.I.S
-- Ejecutar en Supabase SQL Editor. No borra datos existentes.

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

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('INGRESOS', 'Salario', 'income', '["salario", "sueldo", "planilla", "pago semanal", "pago", "nomina", "nómina"]'::jsonb, 10, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('INGRESOS', 'Horas extra', 'income', '["horas extra", "hora extra", "ot", "overtime", "extra"]'::jsonb, 20, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('INGRESOS', 'Bono', 'income', '["bono", "bonus", "comision", "comisión"]'::jsonb, 30, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('INGRESOS', 'Reembolso', 'income', '["reembolso", "devolucion", "devolución", "refund"]'::jsonb, 40, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('INGRESOS', 'Inversión', 'income', '["dividendo", "dividendos", "interes", "interés", "ganancia inversion", "ganancia inversión"]'::jsonb, 50, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('INGRESOS', 'Otros ingresos', 'income', '["otros ingresos", "ingreso extra", "freelance", "venta"]'::jsonb, 60, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('GASTOS FIJOS', 'Vivienda', 'expense', '["alquiler", "renta", "casa", "vivienda", "hipoteca"]'::jsonb, 110, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('GASTOS FIJOS', 'Servicios', 'expense', '["servicios", "agua", "luz", "electricidad", "recibo", "aya", "cnfl", "ice electricidad"]'::jsonb, 120, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('GASTOS FIJOS', 'Internet', 'expense', '["internet", "wifi", "fibra", "kolbi", "telecable", "liberty"]'::jsonb, 130, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('GASTOS FIJOS', 'Teléfono', 'expense', '["telefono", "teléfono", "celular", "linea", "línea", "movil", "móvil"]'::jsonb, 140, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('GASTOS FIJOS', 'Seguros', 'expense', '["seguro", "seguros", "poliza", "póliza", "ins"]'::jsonb, 150, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('GASTOS VARIABLES', 'Comida', 'expense', '["super", "supermercado", "comida", "maxi pali", "maxipalí", "walmart", "mas x menos", "automercado", "pali", "palí", "verduleria", "verdulería"]'::jsonb, 210, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('GASTOS VARIABLES', 'Restaurante', 'expense', '["restaurante", "uber eats", "ubereats", "comida rapida", "comida rápida", "mcdonald", "mcdonalds", "burger", "kfc", "pizza", "soda", "cafeteria", "cafetería"]'::jsonb, 220, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('GASTOS VARIABLES', 'Transporte', 'expense', '["uber", "didi", "taxi", "bus", "transporte", "peaje", "parqueo"]'::jsonb, 230, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('GASTOS VARIABLES', 'Gasolina', 'expense', '["gasolina", "combustible", "bomba", "estacion", "estación", "servicentro"]'::jsonb, 240, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('GASTOS VARIABLES', 'Entretenimiento', 'expense', '["cine", "netflix", "spotify", "playstation", "psn", "juego", "videojuego", "entretenimiento", "salida", "anime"]'::jsonb, 250, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('GASTOS VARIABLES', 'Compras', 'expense', '["compra", "compras", "amazon", "temu", "shein", "ropa", "zapatos", "tienda", "mall"]'::jsonb, 260, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('GASTOS VARIABLES', 'Salud', 'expense', '["salud", "farmacia", "medicina", "doctor", "medico", "médico", "clinica", "clínica", "dentista", "hospital"]'::jsonb, 270, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('GASTOS VARIABLES', 'Mascotas', 'expense', '["mascota", "mascotas", "hamster", "hámster", "veterinaria", "vet", "alimento mascota"]'::jsonb, 280, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('DEUDAS', 'Tarjeta BAC', 'expense', '["bac", "tarjeta bac", "visa bac", "mastercard bac"]'::jsonb, 310, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('DEUDAS', 'MultiMoney', 'expense', '["multimoney", "multi money"]'::jsonb, 320, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('DEUDAS', 'Banco Popular', 'expense', '["banco popular", "popular", "prestamo popular", "préstamo popular"]'::jsonb, 330, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('DEUDAS', 'Familiar', 'expense', '["familiar", "familia", "papa", "papá", "mama", "mamá"]'::jsonb, 340, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('DEUDAS', 'Otros préstamos', 'expense', '["prestamo", "préstamo", "credito", "crédito", "deuda"]'::jsonb, 350, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('AHORRO', 'Fondo emergencia', 'transfer', '["fondo emergencia", "emergencia", "fondo de emergencia"]'::jsonb, 410, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('AHORRO', 'Viajes', 'transfer', '["viaje", "viajes", "ecuador", "japon", "japón", "mexico", "méxico"]'::jsonb, 420, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('AHORRO', 'Meta personal', 'transfer', '["meta", "meta personal", "objetivo", "ahorro"]'::jsonb, 430, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('INVERSIONES', 'IBKR', 'transfer', '["ibkr", "interactive brokers", "acciones", "bolsa"]'::jsonb, 510, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('INVERSIONES', 'Cripto', 'transfer', '["cripto", "crypto", "bitcoin", "btc", "ethereum", "eth", "solana", "sol"]'::jsonb, 520, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

INSERT INTO category_catalog (group_name, category_name, transaction_type, aliases, sort_order, is_active)
VALUES ('INVERSIONES', 'Otros', 'transfer', '["otros", "otra inversion", "otra inversión"]'::jsonb, 530, TRUE)
ON CONFLICT (group_name, category_name)
DO UPDATE SET
    transaction_type = EXCLUDED.transaction_type,
    aliases = EXCLUDED.aliases,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

-- Tarjeta BAC fija por usuario existente: corte 21, pago 5.
INSERT INTO credit_card_settings (user_id, name, cut_day, payment_day, created_at)
SELECT id, 'BAC', 21, 5, NOW()
FROM allowed_users u
WHERE NOT EXISTS (
    SELECT 1
    FROM credit_card_settings c
    WHERE c.user_id = u.id
    AND LOWER(c.name) = 'bac'
);

-- Calendario salarial base: semanal jueves. El salario/hora se agregará luego desde JARVIS.
INSERT INTO pay_schedule (user_id, pay_frequency, pay_day, first_pay_date, notes, created_at)
SELECT id, 'weekly', 'thursday', NULL, 'Pago semanal los jueves. Configuración editable desde JARVIS si cambia de trabajo.', NOW()
FROM allowed_users u
WHERE NOT EXISTS (
    SELECT 1
    FROM pay_schedule p
    WHERE p.user_id = u.id
);
