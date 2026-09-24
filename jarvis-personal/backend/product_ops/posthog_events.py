"""Aggregate DINCR server events for PostHog.

Analytics observes how the product behaves, never the user's financial content.
Every server event is anonymous: a fresh random ``distinct_id`` per event, no
person profile, no IP geolocation, no account/workspace/user identifier. Each
event has a closed list of properties and each property a closed type (enum,
bounded integer or boolean). Anything else is dropped here, before the network,
so a caller cannot leak an amount, a mail subject or a token by mistake. The
full contract, and how to add an event, is in docs/analytics/posthog-event-taxonomy.md.

Delivery is best-effort: without configuration nothing is sent, and a PostHog
failure or timeout never affects the request or job that emitted the event.
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urlsplit

import requests

logger = logging.getLogger(__name__)
HOSTS = frozenset({"us.i.posthog.com", "eu.i.posthog.com"})

PROVIDERS = frozenset({"gmail", "microsoft"})
ENUMS: dict[str, frozenset[str]] = {
    "provider": PROVIDERS,
    # What started a mailbox sync: the user, the first sync after connecting,
    # the maintenance cron or a provider push notification.
    "trigger": frozenset({"manual", "connect", "maintenance", "push"}),
    "scan_scope": frozenset({"recent", "current_month", "current_year", "year_to_date"}),
    "error_code": frozenset({"reauth_required", "provider_error", "access_denied", "internal"}),
    "method": frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"}),
    "plan": frozenset({"free", "basic", "vip", "owner"}),
    "billing_period": frozenset({"monthly", "annual"}),
    "subscription_event": frozenset({
        "trial_started", "purchased", "renewed", "upgrade", "downgrade", "cancel_requested",
        "grace_period", "restored", "expired", "revoked",
    }),
    "store": frozenset({"sandbox", "apple", "google"}),
}
COUNTS = frozenset({"messages_scanned", "candidates_pending", "duplicates", "payroll_reports", "ignored", "count"})
BOOLEANS = frozenset({"success", "initial_scan_complete"})
# Route templates come from code (`/user-product/vip/gmail/{connection_id}`), never
# from the request URL, so they carry no identifiers or query strings.
ROUTE_TEMPLATE = re.compile(r"^/[a-z0-9_/{}-]{0,120}$")
EXCEPTION_TYPE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,60}$")

# Event -> the properties it may carry (besides the common ones added below).
SERVER_EVENTS: dict[str, frozenset[str]] = {
    "gmail_connected": frozenset(),
    "account_deletion_completed": frozenset(),
    "mail_sync_completed": frozenset({"provider", "trigger", "scan_scope", "initial_scan_complete", "duration_ms", *COUNTS}),
    "mail_sync_failed": frozenset({"provider", "trigger", "error_code", "duration_ms"}),
    "server_error": frozenset({"route", "method", "status_code", "exception_type"}),
    "subscription_changed": frozenset({"plan", "billing_period", "subscription_event", "store"}),
    # One-time historical baseline (backend/scripts/posthog_signups_baseline.py): new accounts per day.
    "baseline_daily_signups": frozenset({"count"}),
}
_ALWAYS_SUCCESSFUL = frozenset({"gmail_connected", "account_deletion_completed", "mail_sync_completed", "subscription_changed", "baseline_daily_signups"})
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="dincr-analytics")


def analytics_environment() -> str:
    """production / staging / development: explicit, else inferred (Render = production)."""
    configured = os.getenv("ANALYTICS_ENVIRONMENT", "").strip().lower()
    if configured in {"production", "staging", "development"}:
        return configured
    return "production" if os.getenv("RENDER", "").strip().lower() == "true" else "development"


def safe_server_properties(event_name: str, properties: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only this event's allowlisted properties with valid, non-sensitive values."""
    allowed = SERVER_EVENTS.get(event_name, frozenset())
    safe: dict[str, Any] = {}
    for name, value in (properties or {}).items():
        if name not in allowed:
            continue
        if name in ENUMS and isinstance(value, str) and value in ENUMS[name]:
            safe[name] = value
        elif name in BOOLEANS and isinstance(value, bool):
            safe[name] = value
        elif name in COUNTS and isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            safe[name] = min(value, 100_000)
        elif name == "duration_ms" and isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            safe[name] = min(int(round(value / 100.0)) * 100, 600_000)
        elif name == "status_code" and isinstance(value, int) and not isinstance(value, bool) and 100 <= value <= 599:
            safe[name] = value
        elif name == "route" and isinstance(value, str) and ROUTE_TEMPLATE.match(value):
            safe[name] = value
        elif name == "exception_type" and isinstance(value, str) and EXCEPTION_TYPE.match(value):
            safe[name] = value
    return safe


def _configuration() -> tuple[str, str] | None:
    key = os.getenv("POSTHOG_API_KEY", "").strip()
    host = os.getenv("POSTHOG_HOST", "").strip().rstrip("/")
    parsed = urlsplit(host)
    if (not key or parsed.scheme != "https" or parsed.netloc not in HOSTS
            or parsed.path or parsed.query or parsed.fragment):
        return None
    return key, host


def build_payload(event_name: str, properties: dict[str, Any] | None, key: str) -> dict[str, Any] | None:
    if event_name not in SERVER_EVENTS:
        return None
    safe = safe_server_properties(event_name, properties)
    success = safe.pop("success", event_name in _ALWAYS_SUCCESSFUL)
    return {
        "api_key": key,
        "event": event_name,
        # Fresh per event: no account identifier or durable person profile.
        # $process_person_profile=False stops PostHog from creating a person
        # for each random id; the request IP is Render's, not the user's.
        "distinct_id": f"dincr_server_{uuid.uuid4().hex}",
        "properties": {
            **safe,
            "success": bool(success),
            "source_type": "server",
            "environment": analytics_environment(),
            "$process_person_profile": False,
            "$geoip_disable": True,
        },
    }


def capture_backend_event(event_name: str, properties: dict[str, Any] | None = None) -> None:
    """Send one sanitized event now (call it from BackgroundTasks or a worker)."""
    configuration = _configuration()
    if not configuration:
        return
    key, host = configuration
    payload = build_payload(event_name, properties, key)
    if payload is None:
        return
    try:
        response = requests.post(f"{host}/capture/", json=payload, timeout=(0.5, 1.5))
        response.raise_for_status()
    except requests.RequestException:
        logger.warning("DINCR aggregate analytics unavailable")


def capture_backend_event_later(event_name: str, properties: dict[str, Any] | None = None) -> None:
    """Queue an event from code that has no BackgroundTasks (syncs, crons, handlers).

    Returns immediately; nothing is queued when analytics is not configured.
    """
    if not _configuration() or event_name not in SERVER_EVENTS:
        return
    try:
        _executor.submit(capture_backend_event, event_name, dict(properties or {}))
    except RuntimeError:  # interpreter shutting down
        pass
