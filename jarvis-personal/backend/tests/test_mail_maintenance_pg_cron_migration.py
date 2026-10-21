"""The in-database mail maintenance scheduler (pg_cron + pg_net) keeps its security properties.

It cannot run here (no pg_cron outside Supabase), so these checks read the SQL: no secret or host
in the file, both functions private and SECURITY DEFINER with a fixed search_path, nobody but the
owner may execute them, a missing setting fails loudly, the schedule is an idempotent upsert, and
the rollback removes exactly what the migration adds.
"""
import re
from pathlib import Path

DATABASE = Path(__file__).resolve().parents[2] / "database"
NAME = "20261021170000_mail_maintenance_pg_cron"
SQL = (DATABASE / "migrations" / f"{NAME}.sql").read_text(encoding="utf-8")
ROLLBACK = (DATABASE / "rollback" / f"{NAME}_rollback.sql").read_text(encoding="utf-8")
CODE = "\n".join(line for line in SQL.splitlines() if not line.lstrip().startswith("--"))
FUNCTIONS = ["run_mail_maintenance", "prune_mail_maintenance_runs"]


def function_body(name: str) -> str:
    return re.search(rf"CREATE OR REPLACE FUNCTION dincr_private\.{name}\(\)(.*?)\$fn\$;", CODE, re.S).group(1)


def test_no_secret_host_or_token_is_written_in_the_migration():
    assert not re.search(r"https://[a-z0-9.-]+\.[a-z]{2,}", CODE, re.I), "the backend URL comes from Vault"
    assert "vault.create_secret" not in CODE, "the Owner creates the Vault secrets; the migration never holds them"
    assert re.search(r"name = 'dincr_mail_maintenance_secret'", CODE)
    assert re.search(r"name = 'dincr_backend_url'", CODE)


def test_functions_are_private_definer_with_a_fixed_search_path():
    for name in FUNCTIONS:
        body = function_body(name)
        assert "SECURITY DEFINER" in body and "SET search_path = pg_catalog, pg_temp" in body, name
        assert f"ALTER FUNCTION dincr_private.{name}() OWNER TO postgres;" in CODE
        assert f"REVOKE ALL ON FUNCTION dincr_private.{name}() FROM PUBLIC;" in CODE
        assert f"REVOKE ALL ON FUNCTION dincr_private.{name}() FROM anon, authenticated;" in CODE
        assert f"REVOKE ALL ON FUNCTION dincr_private.{name}() FROM dincr_app;" in CODE
    assert not re.search(r"GRANT\s+EXECUTE", CODE, re.I), "nobody else may trigger maintenance"


def test_a_missing_setting_fails_the_run_instead_of_a_silent_no_op():
    body = function_body("run_mail_maintenance")
    assert re.search(r"RAISE EXCEPTION 'mail maintenance not configured", body)
    assert "'^https://" in body, "only an https base URL is called"
    assert "'X-Finva-Cron-Secret', v_secret" in body and "/user-product/vip/gmail/maintenance" in body
    assert "timeout_milliseconds := 300000" in body


def test_the_schedule_is_an_idempotent_upsert_and_pruning_touches_only_these_jobs():
    assert "SELECT cron.schedule('dincr-mail-maintenance', '*/10 * * * *', 'SELECT dincr_private.run_mail_maintenance()');" in CODE
    prune = function_body("prune_mail_maintenance_runs")
    assert "jobname IN ('dincr-mail-maintenance', 'dincr-mail-maintenance-prune')" in prune
    assert re.search(r"DELETE FROM cron\.job_run_details", prune)
    # Mail, candidates and transactions are never touched by the scheduler itself.
    for table in ("finva_email_messages", "finva_email_candidates", "transactions", "finva_gmail_connections"):
        assert table not in CODE


def test_the_rollback_removes_exactly_what_the_migration_adds():
    for job in ("dincr-mail-maintenance", "dincr-mail-maintenance-prune"):
        assert f"PERFORM cron.unschedule('{job}');" in ROLLBACK
    for name in FUNCTIONS:
        assert f"DROP FUNCTION IF EXISTS dincr_private.{name}();" in ROLLBACK
    assert "DROP EXTENSION" not in ROLLBACK.upper().replace("-- ", "")
