"""Labs refuses every environment that could reach production (fail closed)."""
from __future__ import annotations

import pytest

from labs import guard
from labs.tests import adversarial


@pytest.mark.parametrize("name", sorted(adversarial.REFUSED_DSNS))
def test_labs_rejects_non_local_or_production_databases(name):
    with pytest.raises(guard.LabsRefused):
        guard.check_database_url(adversarial.REFUSED_DSNS[name])


@pytest.mark.parametrize("name", sorted(adversarial.ACCEPTED_DSNS))
def test_labs_accepts_only_local_labs_databases(name):
    assert guard.check_database_url(adversarial.ACCEPTED_DSNS[name])


@pytest.mark.parametrize("name", sorted(adversarial.REFUSED_ENVIRONMENTS))
def test_labs_rejects_production_settings(name):
    with pytest.raises(guard.LabsRefused):
        guard.check_environment(adversarial.REFUSED_ENVIRONMENTS[name])


def test_a_clean_labs_environment_is_accepted():
    assert guard.check_environment(adversarial.labs_env()) == adversarial.LOCAL_DSN
    assert guard.check_environment(adversarial.labs_env(DATABASE_URL=adversarial.LOCAL_DSN)) == adversarial.LOCAL_DSN


def test_refusals_name_settings_but_never_print_values():
    secret = "sk-this-must-never-be-printed"
    with pytest.raises(guard.LabsRefused) as refused:
        guard.check_environment(adversarial.labs_env(SUPABASE_SERVICE_ROLE_KEY=secret))
    assert "SUPABASE_SERVICE_ROLE_KEY" in str(refused.value) and secret not in str(refused.value)
    with pytest.raises(guard.LabsRefused) as refused:
        guard.check_database_url("postgresql://user:hunter2@db.abcdefghijkl.supabase.co/dincr_labs")
    assert "hunter2" not in str(refused.value)


def test_every_setting_the_backend_reads_for_an_external_service_is_forbidden():
    """A setting added to the backend for a new service must be refused by Labs (or consciously allowed)."""
    import re
    from pathlib import Path

    backend = Path(__file__).resolve().parents[2] / "backend"
    names = set()
    for path in backend.rglob("*.py"):
        if "tests" in path.parts or path.name.startswith("test_"):
            continue
        text = path.read_text(encoding="utf-8")
        names |= set(re.findall(r"os\.(?:getenv|environ\.get)\(\s*[\"']([A-Z0-9_]+)[\"']", text))
        if "getenv" in text or "environ" in text:  # names kept in tuples/dicts (e.g. CONFIG_NAMES) and read later
            names |= {c for c in re.findall(r"[\"']([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)[\"']", text)
                      if re.search(r"CLIENT_ID|CLIENT_SECRET|REDIRECT|_URI$|_URL$|_KEY$|_HOST$|_EMAILS?$|TOKEN|SECRET|PASSWORD|WEBHOOK", c)}
    harmless = {  # settings that neither hold a credential nor point at a real service
        "DATABASE_URL", "DINCR_DB_APPLICATION_NAME", "DINCR_DB_POOL_IDLE_SECONDS", "DINCR_DB_POOL_MAX_AGE_SECONDS",
        "DINCR_DB_POOL_MAX_IDLE", "DINCR_PGSERVER_DIR", "DINCR_REQUIRE_PG_TESTS", "ANALYTICS_ENVIRONMENT",
        "BAC_CARD_CUT_DAY", "EMAIL_AUTO_COMMIT_CONFIDENCE", "USD_CRC_FALLBACK", "DINCR_AUTH_PROVIDERS",
        "DINCR_APPLE_ENVIRONMENTS", "FINVA_STORE_TRIAL_DAYS", "FINVA_BASIC_ANNUAL_CRC", "FINVA_VIP_ANNUAL_CRC",
        "FINVA_BASIC_ANNUAL_PRODUCT_ID", "FINVA_BASIC_MONTHLY_PRODUCT_ID", "FINVA_VIP_ANNUAL_PRODUCT_ID",
        "FINVA_VIP_MONTHLY_PRODUCT_ID", "FINVA_APPLE_BUNDLE_ID", "FINVA_GOOGLE_PACKAGE_NAME",
        "JARVIS_OWNER_BRIDGE_TOKEN_TTL_SECONDS",
        "PARSER_DISCOVERY_ENABLED",
        "IGNORED_EMAIL", "MISSING_KEY",  # status constants in env-reading modules, not settings
    }
    unguarded = sorted(n for n in names - harmless if not guard.forbidden_settings({n: "x"}))
    assert unguarded == [], f"classify these new backend settings in labs/guard.py (forbid) or here (harmless): {unguarded}"
