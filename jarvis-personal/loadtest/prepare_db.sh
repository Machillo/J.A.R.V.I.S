#!/usr/bin/env bash
# Build an isolated local database for load tests: production SCHEMA + catalog rows only.
# No personal or financial row is copied; users and their data are synthetic (seeded through the API).
#
#   DINCR_SCHEMA_DUMP=<pg_dump -Fc file> PG_BIN=/opt/homebrew/opt/postgresql@17/bin ./loadtest/prepare_db.sh [dbname]
#
# DINCR_SCHEMA_DUMP: a custom-format dump of production (e.g. a BACKUP_VERIFIED dump.pgc). Only its
# schema and the catalog tables below are restored. Migrations newer than the dump are applied from
# database/migrations when MIGRATIONS_AFTER lists them.
set -euo pipefail
DB="${1:-dincr_load}"
: "${DINCR_SCHEMA_DUMP:?set DINCR_SCHEMA_DUMP to a pg_dump -Fc file}"
PG="${PG_BIN:-}"; [ -n "$PG" ] && PG="$PG/"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
CATALOG_TABLES=(plans features plan_features category_catalog app_release_policies)
PYTHON="${PYTHON:-python3}"

"${PG}psql" -X -q -d postgres -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS \"$DB\" WITH (FORCE)" -c "CREATE DATABASE \"$DB\""
"${PG}psql" -X -q -d "$DB" -v ON_ERROR_STOP=1 <<'SQL'
DO $$ BEGIN CREATE ROLE anon NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE authenticated NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE service_role NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS pgcrypto SCHEMA extensions;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp" SCHEMA extensions;
CREATE SCHEMA auth;
CREATE TABLE auth.users (id uuid PRIMARY KEY);
CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $f$ SELECT NULL::uuid $f$;
CREATE SCHEMA vault;
CREATE TABLE vault.secrets (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), secret text, name text, description text);
CREATE VIEW vault.decrypted_secrets AS SELECT id, secret AS decrypted_secret, name FROM vault.secrets;
CREATE FUNCTION vault.create_secret(new_secret text, new_name text DEFAULT NULL, new_description text DEFAULT NULL)
  RETURNS uuid LANGUAGE sql AS $f$ INSERT INTO vault.secrets(secret, name, description) VALUES (new_secret, new_name, new_description) RETURNING id $f$;
SQL
"${PG}pg_restore" --schema-only --no-owner --no-privileges --schema=public -d "$DB" "$DINCR_SCHEMA_DUMP" 2>/dev/null || true
for table in "${CATALOG_TABLES[@]}"; do
  "${PG}pg_restore" --data-only --no-owner --schema=public --table="$table" -d "$DB" "$DINCR_SCHEMA_DUMP" 2>/dev/null || true
done
# Feature flags: every flag enabled (the production rows reference an Owner account that is not copied).
(cd "$HERE" && "$PYTHON" - <<'PY'
from backend.core.feature_flags import FEATURE_DEFINITIONS
def q(value): return "'" + str(value).replace("'", "''") + "'"
for key, d in FEATURE_DEFINITIONS.items():
    print("INSERT INTO app_feature_flags(flag_key,display_name,description,enabled,safe_default_enabled,disabled_message_es,disabled_message_en) "
          f"VALUES ({q(key)},{q(d['display_name'])},{q('Load test: enabled')},TRUE,{str(d['safe_default_enabled']).upper()},"
          f"{q(d['message_es'])},{q(d['message_en'])}) ON CONFLICT (flag_key) DO UPDATE SET enabled=TRUE;")
PY
) | "${PG}psql" -X -q -d "$DB" -v ON_ERROR_STOP=1
for migration in ${MIGRATIONS_AFTER:-}; do
  "${PG}psql" -X -q -d "$DB" -v ON_ERROR_STOP=1 -f "$HERE/database/migrations/$migration" >/dev/null
done
"${PG}psql" -X -At -d "$DB" -c "SELECT 'tables=' || count(*) FROM pg_tables WHERE schemaname='public'" \
  -c "SELECT 'catalog: plans=' || (SELECT count(*) FROM plans) || ' features=' || (SELECT count(*) FROM features) || ' flags=' || (SELECT count(*) FROM app_feature_flags)" \
  -c "SELECT 'personal rows (must be 0): ' || (SELECT count(*) FROM accounts) + (SELECT count(*) FROM allowed_users) + (SELECT count(*) FROM transactions)"
