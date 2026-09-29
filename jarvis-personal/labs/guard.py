"""DINCR Labs environment identity and production guard (fail closed).

Labs runs only when all of these hold, checked before any backend module is
imported and again before every destructive operation:

1. ``DINCR_ENV`` is exactly ``labs``. Nothing else means Labs: not "dev", not
   "test", not unset.
2. No production credential or production-reaching setting is present in the
   process environment (checked by name; values are never read or printed).
3. The Labs database is local: the DSN host is a loopback address or a local
   socket directory, the database name starts with ``dincr_labs``, and the DSN
   contains no known production marker (hosting domains, the product domain).

The comparison uses only public, non-secret identifiers. Allowing only local
databases is the primary control; the production markers are defence in depth
for the case "I thought I was in Labs but DATABASE_URL was production".
"""
from __future__ import annotations

import ipaddress
import os
import re
from collections.abc import Mapping
from urllib.parse import parse_qs, unquote, urlsplit

LABS_ENV_VALUE = "labs"
LABS_DB_PREFIX = "dincr_labs"

# Public hostnames and domain fragments that identify hosted DINCR infrastructure.
# Any DSN or URL containing one is production (or a cloud resource Labs must not
# create or reach). Keep lower case; see docs/labs.md "Maintaining the guard".
PRODUCTION_MARKERS = (
    "supabase.co",
    "supabase.com",
    "supabase.in",
    "pooler.supabase",
    "onrender.com",
    "render.com",
    "vercel.app",
    "workers.dev",
    "dincr.com",
    "dincr.app",
    "googleapis.com",
    "graph.microsoft.com",
    "apple.com",
    "discord.com",
    "discordapp.com",
    "posthog.com",
)

# Settings that carry a production credential or point the backend at a real
# external service. Labs refuses to start while any of them is set (even empty
# strings count as "set": a template left in a shell is still a mistake).
FORBIDDEN_EXACT = frozenset({
    "SUPABASE_URL", "SUPABASE_ANON_KEY", "SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY",
    "FINVA_GMAIL_CLIENT_ID", "FINVA_GMAIL_CLIENT_SECRET", "FINVA_GMAIL_REDIRECT_URI", "FINVA_GMAIL_RETURN_URL",
    "FINVA_GMAIL_PUBSUB_TOPIC", "FINVA_GMAIL_PUBSUB_VERIFICATION_TOKEN", "FINVA_GMAIL_CRON_SECRET",
    "GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET",
    "DINCR_GOOGLE_PLAY_SERVICE_ACCOUNT_JSON", "DINCR_GOOGLE_RTDN_AUDIENCE", "DINCR_GOOGLE_RTDN_SERVICE_ACCOUNT",
    "DINCR_STORE_CRON_SECRET", "DINCR_STORE_SANDBOX_ACCOUNT_IDS", "DINCR_STORE_ACCEPT_SANDBOX", "DINCR_STORE_SIMULATOR",
    "FINVA_BILLING_SMOKE_ALLOW", "FINVA_BILLING_SMOKE_LEGACY_USER_ID",
    "SUPPORT_DISCORD_WEBHOOK_URL", "SUPPORT_SMTP_HOST", "SUPPORT_SMTP_USER", "SUPPORT_SMTP_APP_PASSWORD",
    "SUPPORT_SMTP_FROM", "SUPPORT_EMAIL_TO",
    "VAPID_PRIVATE_KEY", "VAPID_PUBLIC_KEY", "VAPID_SUBJECT",
    "POSTHOG_API_KEY", "POSTHOG_HOST",
    "SERPER_API_KEY", "TAVILY_API_KEY", "PARSER_DISCOVERY_MODEL",  # AI provider keys: see FORBIDDEN_PREFIXES
    "IBKR_FLEX_TOKEN", "IBKR_FLEX_QUERY_ID", "IBKR_BRIDGE_SECRET", "IBKR_FLEX_CRON_SECRET",
    "JARVIS_OWNER_BRIDGE_API_KEY", "OWNER_EMAIL", "OWNER_EMAILS", "OWNER_DISPLAY_NAME",
    "EMAIL_MONITOR_CRON_SECRET", "NOTIFICATION_CRON_SECRET", "DEPLOYMENT_WEBHOOK_SECRET", "RENDER_WEBHOOK_SECRET",
    "RENDER", "RENDER_SERVICE_ID", "RENDER_EXTERNAL_URL", "VERCEL", "VERCEL_ENV", "CF_PAGES",
    "DINCR_TEST_POSTGRES_URL", "SRC_DSN", "OTHER_DSN",
})
# Whole families of settings: hosted services, Owner-private configuration
# (names, card aliases, own accounts and contacts are personal data) and real
# mail providers. A new setting in one of these families is refused by default.
FORBIDDEN_PREFIXES = (
    "SUPABASE_", "VITE_SUPABASE_", "VITE_API_URL", "VITE_NATIVE_API_URL", "VITE_POSTHOG",
    "OWNER_", "JARVIS_OWN", "JARVIS_CARD_ALIASES", "JARVIS_RECEIVABLE", "JARVIS_USERS_API", "JARVIS_ADMIN",
    "GMAIL_", "FINVA_GMAIL_", "MICROSOFT_", "FINVA_SINPE_", "FINVA_ISOLATION", "PERSONAL_ISOLATION",
    "DINCR_STORE_", "DINCR_GOOGLE_", "FINVA_BILLING_", "SUPPORT_SMTP_", "SUPPORT_DISCORD_", "SUPPORT_EMAIL",
    "POSTHOG_", "VAPID_", "IBKR_", "RENDER", "VERCEL", "CF_", "CLOUDFLARE_", "OPENAI_", "ANTHROPIC_", "GEMINI",
    "GOOGLE_APPLICATION_CREDENTIALS", "AWS_", "AZURE_",
)
# Any other name that looks like a credential is refused too (fail closed on
# settings added to the backend after this file was written).
FORBIDDEN_PATTERN = re.compile(
    r"(SECRET|PASSWORD|PASSWD|TOKEN|PRIVATE_KEY|API_KEY|SERVICE_ACCOUNT|WEBHOOK|CREDENTIAL|DSN$|_JWT)", re.I,
)
# Names that match the pattern but are Labs' own, harmless settings.
ALLOWED_NAMES = frozenset({"DINCR_LABS_DATABASE_URL"})


class LabsRefused(RuntimeError):
    """Labs refuses to run: the environment is not provably isolated."""


def forbidden_settings(environ: Mapping[str, str]) -> list[str]:
    """Names (never values) of production settings present in ``environ``."""
    found = []
    for name in environ:
        upper = name.upper()
        if upper in ALLOWED_NAMES:
            continue
        if upper in FORBIDDEN_EXACT or upper.startswith(FORBIDDEN_PREFIXES) or FORBIDDEN_PATTERN.search(upper):
            found.append(name)
    return sorted(found)


def _is_loopback(host: str) -> bool:
    if host.lower() in {"localhost", "localhost.localdomain"}:
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def _is_local_socket_dir(host: str) -> bool:
    # libpq treats a host starting with "/" (or a Windows drive path) as a socket directory.
    return host.startswith("/") or bool(re.match(r"^[A-Za-z]:[\\/]", host))


def production_markers_in(text: str) -> list[str]:
    lowered = unquote(text or "").lower()
    return [marker for marker in PRODUCTION_MARKERS if marker in lowered]


def check_database_url(dsn: str) -> str:
    """Return the DSN if it is a local Labs database; raise LabsRefused otherwise."""
    if not dsn or not dsn.strip():
        raise LabsRefused("no Labs database URL (run `python -m labs up`)")
    markers = production_markers_in(dsn)
    if markers:
        raise LabsRefused(f"the database URL names hosted infrastructure ({', '.join(markers)}); Labs is local only")
    parts = urlsplit(dsn.strip())
    # A local port forwarded to a hosted pooler (ssh -L, a proxy) looks like 127.0.0.1;
    # the pooler's login name gives it away: postgres.<project ref>.
    if re.fullmatch(r"postgres\.[a-z0-9]{15,}", unquote(parts.username or "")):
        raise LabsRefused("the database user is a hosted pooler login (a tunnel to hosted Postgres?); Labs is local only")
    if parts.scheme not in {"postgresql", "postgres"}:
        raise LabsRefused("the Labs database URL must be a postgresql:// URL")
    query = parse_qs(parts.query)
    hosts = [h for h in (parts.hostname or "").split(",") if h] + query.get("host", []) + query.get("hostaddr", [])
    if not hosts:
        raise LabsRefused("the Labs database URL must name a local host (127.0.0.1, localhost or a socket directory)")
    for host in hosts:
        host = unquote(host)
        if not (_is_loopback(host) or _is_local_socket_dir(host)):
            raise LabsRefused("the Labs database host is not local; Labs never connects to a remote database")
    for option in ("service", "passfile", "sslrootcert"):
        if option in query:
            raise LabsRefused(f"the Labs database URL may not use '{option}' (it can redirect the connection)")
    name = unquote(parts.path.lstrip("/"))
    if not name.startswith(LABS_DB_PREFIX):
        raise LabsRefused(f"the Labs database name must start with '{LABS_DB_PREFIX}'")
    return dsn.strip()


def check_environment(environ: Mapping[str, str] | None = None) -> str:
    """Validate the whole Labs environment; return the Labs database URL."""
    environ = os.environ if environ is None else environ
    if environ.get("DINCR_ENV") != LABS_ENV_VALUE:
        raise LabsRefused("DINCR_ENV must be exactly 'labs' (it is the only value that enables Labs)")
    forbidden = forbidden_settings(environ)
    if forbidden:
        raise LabsRefused("production settings are present in this environment: " + ", ".join(forbidden)
                          + ". Open a clean shell for Labs (see docs/labs.md).")
    dsn = environ.get("DINCR_LABS_DATABASE_URL", "")
    backend_dsn = environ.get("DATABASE_URL", "")
    if backend_dsn and backend_dsn.strip() != dsn.strip():
        raise LabsRefused("DATABASE_URL is set and differs from the Labs database; unset it in the Labs shell")
    for name in ("PGHOST", "PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE", "PGPASSFILE", "PGDATABASE"):
        if environ.get(name):
            raise LabsRefused(f"{name} is set; libpq could redirect Labs connections. Unset it in the Labs shell")
    return check_database_url(dsn)
