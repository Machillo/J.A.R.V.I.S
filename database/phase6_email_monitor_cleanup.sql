-- Limpieza segura de la prueba anterior del monitor de correos.
-- Borra solo transacciones creadas automáticamente por email_monitor.
DELETE FROM transactions
WHERE source ILIKE 'email_monitor'
   OR source ILIKE '%email%'
   OR source ILIKE '%gmail%';

-- Resetea candidatos y correos ya ingeridos para poder re-escanear con el parser corregido.
TRUNCATE TABLE email_transaction_candidates RESTART IDENTITY CASCADE;
TRUNCATE TABLE email_ingested_messages RESTART IDENTITY CASCADE;

UPDATE email_monitor_settings
SET last_scan_at = NULL,
    updated_at = NOW();
