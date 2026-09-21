-- Remove the deferred Phase 1F AI fallback. Deterministic parsers remain active.

BEGIN;

DROP TABLE IF EXISTS public.finva_parser_fallback_events;

ALTER TABLE public.finva_gmail_connections
    DROP COLUMN IF EXISTS ai_fallback_enabled,
    DROP COLUMN IF EXISTS ai_fallback_consent_at;

COMMIT;
