-- Fase 6.3 - Limpieza segura para reanalizar correos con el parser bancario por plantillas.
-- Borra SOLO artefactos del monitor de correos que no hayan sido guardados como transacciones.
-- Después de ejecutarlo, usa el botón "Escanear correos del mes actual" otra vez.

WITH owner AS (
    SELECT id
    FROM users
    WHERE email = 'gatotico99@gmail.com'
    LIMIT 1
), protected_messages AS (
    SELECT DISTINCT email_message_id
    FROM email_transaction_candidates
    WHERE user_id = (SELECT id FROM owner)
      AND transaction_id IS NOT NULL
      AND email_message_id IS NOT NULL
)
DELETE FROM email_ingested_messages
WHERE user_id = (SELECT id FROM owner)
  AND provider = 'gmail'
  AND id NOT IN (SELECT email_message_id FROM protected_messages)
  AND created_at >= NOW() - INTERVAL '60 days';

-- Garantiza que el auto guardado siga desactivado mientras validamos lectura limpia.
UPDATE email_monitor_settings
SET auto_commit_confidence = 999,
    updated_at = NOW()
WHERE user_id = (SELECT id FROM owner);
