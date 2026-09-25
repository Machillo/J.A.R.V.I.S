#!/usr/bin/env bash
# Start the backend under test against the isolated database, with a clean environment.
#   PYTHON=<python with backend deps> DB=dincr_load DB_PORT=55432 WORKERS=1 ./loadtest/start_backend.sh
set -euo pipefail
cd "$(dirname "$0")/.."
exec env -i PATH=/usr/bin:/bin HOME="${TMPDIR:-/tmp}" \
  DATABASE_URL="host=127.0.0.1 port=${DB_PORT:-55432} dbname=${DB:-dincr_load} sslmode=disable user=${DB_USER:-$USER}" \
  SUPABASE_URL="http://127.0.0.1:${AUTH_STUB_PORT:-8791}" SUPABASE_ANON_KEY=local-anon-not-a-secret \
  DINCR_DB_APPLICATION_NAME=dincr-backend ${EXTRA_ENV:-} \
  "${PYTHON:-python3}" -m uvicorn backend.main:app --host 127.0.0.1 --port "${PORT:-8790}" --workers "${WORKERS:-1}" --log-level warning
