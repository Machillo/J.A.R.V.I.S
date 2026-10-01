"""Product analytics relay for the native apps (contract v2).

The native iOS/Android apps have no PostHog SDK and hold no PostHog key. They send
v2 product events to ``POST /product-ops/analytics``; this module validates them
against the same closed contract as ``frontend/src/lib/analyticsContract.js``
(parity is enforced by ``test_analytics_relay.py``) and forwards the survivors to
PostHog with the server's existing configuration.

What the server decides, never the client:
- the audience: ``user`` (Free/Basic/VIP with the current legal acceptance),
  ``owner`` (current legal acceptance; JARVIS navigation events only) or nothing
  (admin, missing acceptance, unknown plan);
- the plan and the environment.

Identity is the app install's random UUID (the native equivalent of posthog-js's
anonymous device ID). It is forwarded as ``distinct_id`` and never stored, logged
or combined with an account, workspace or user identifier. Nothing is written to
the database: the relay only reads the caller's role, plan and legal status.
"""

from __future__ import annotations

import re
from typing import Any

from backend.auth.current_user import get_current_user
from backend.auth.legal import legal_status
from backend.core.database import get_connection
from backend.product_ops.posthog_events import analytics_environment, capture_prepared_later, is_configured

# --- Contract v2 (mirror of frontend/src/lib/analyticsContract.js) -----------------------------

USER_EVENTS = frozenset({
    "app_opened", "app_resumed", "screen_viewed", "login_completed", "logout",
    "onboarding_started", "onboarding_completed", "plan_selected", "plan_access_granted",
    "financial_profile_saved", "useful_action", "strategy_tool_opened",
    "mailbox_connection_started", "mailbox_connected", "mailbox_connection_failed",
    "mailbox_disconnected", "mail_sync_requested", "mail_candidate_reviewed",
    "financial_account_reviewed",
    "account_deletion_started", "account_deletion_failed", "data_export_completed",
    "api_error", "app_error",
})
OWNER_EVENTS = frozenset({"jarvis_opened", "jarvis_section_viewed"})

MAIL_OAUTH_ERROR_CODES = frozenset({
    "denied", "invalid_state", "expired", "exchange_failed", "vip_required",
    "already_processed", "completion_pending", "completion_failed", "other",
})
USER_SCREENS = frozenset({
    "overview", "finance", "plan", "advisor", "profile", "debts", "strategy", "gmail", "accounts",
    "goals", "savings", "transactions", "situation", "more", "settings", "plan-settings", "budget",
    "calendar", "recurring", "reports", "monthly", "feedback", "vip-recommendation", "vip-projections",
    "vip-projection-detail", "vip-scenarios", "vip-reality", "vip-monthly-review", "vip-today",
    "vip-emergency", "vip-aguinaldo", "vip-preferences",
})
JARVIS_SECTIONS = frozenset({
    "dashboard", "finance", "receivables", "wealth", "financialAccounts", "netWorth", "financialTimeline",
    "reconciliation", "deterioration", "investments", "businesses", "goals", "transactions", "memory",
    "strategy", "additionalCards", "emails", "settings", "chats", "moneyControl", "userManagement",
    "productOperations", "profile",
    "chat", "calendar", "money", "money_control", "records",
})
USEFUL_ACTION_TYPES = frozenset({
    "financial_profile_saved", "income_added", "income_updated", "expense_added", "expense_updated",
    "debt_added", "debt_updated", "debt_payment_recorded", "salvavidas_saved", "goal_created",
    "goal_updated", "goal_contribution_recorded", "savings_plan_created", "savings_plan_updated",
    "savings_contribution_recorded", "transaction_added", "transaction_updated", "budget_saved",
    "recurring_added", "recurring_updated", "mail_candidate_reviewed",
})

# Categories a client may send. audience, plan, client and environment are set here.
CLIENT_CATEGORIES: dict[str, frozenset[str]] = {
    "screen": USER_SCREENS,
    "jarvis_section": JARVIS_SECTIONS,
    "access_type": frozenset({"free", "promotion"}),
    "plan_change": frozenset({"immediate", "scheduled", "kept"}),
    "decision": frozenset({"accepted", "corrected", "rejected"}),
    "review_latency": frozenset({"under_1h", "under_1d", "under_7d", "over_7d"}),
    "ownership_status": frozenset({"own", "not_mine"}),
    "provider": frozenset({"gmail", "microsoft"}),
    "error_code": MAIL_OAUTH_ERROR_CODES,
    "action_type": USEFUL_ACTION_TYPES,
    "strategy_tool": frozenset({"salvavidas", "investments", "debts", "distribution", "aguinaldo"}),
    "endpoint": frozenset({"auth", "home", "transactions", "debts", "goals", "budget", "strategy", "reports", "mail",
                           "accounts", "notifications", "settings", "support", "billing", "other"}),
    "method": frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"}),
    "error_category": frozenset({"window_error", "unhandled_rejection", "render_error", "network", "server", "client"}),
}
SERVER_CATEGORIES: dict[str, frozenset[str]] = {
    "plan": frozenset({"free", "basic", "vip"}),
    "audience": frozenset({"user", "owner"}),
    "platform": frozenset({"android", "ios"}),
    "client": frozenset({"capacitor", "native"}),
    "environment": frozenset({"production", "staging", "development"}),
}
CLIENT_BOOLEANS = frozenset({"success"})

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
APP_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def safe_client_properties(properties: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only allow-listed client properties with valid closed values."""
    safe: dict[str, Any] = {}
    for name, value in (properties or {}).items():
        if name in CLIENT_CATEGORIES and isinstance(value, str) and value in CLIENT_CATEGORIES[name]:
            safe[name] = value
        elif name in CLIENT_BOOLEANS and isinstance(value, bool):
            safe[name] = value
        elif name == "status_code" and isinstance(value, int) and not isinstance(value, bool) and 100 <= value <= 599:
            safe[name] = value
    return safe


def audience_of(user: dict[str, Any]) -> tuple[str | None, str | None]:
    """(audience, plan) from the server's own records; (None, None) means nothing is sent."""
    role = user.get("role")
    account_id = user.get("account_id")
    if role not in {"user", "owner"} or not account_id:
        return None, None
    with get_connection() as conn:
        if legal_status(conn, str(account_id))["required"]:
            return None, None
        if role == "owner":
            return "owner", None
        row = conn.execute(
            "SELECT p.code FROM account_subscriptions s JOIN plans p ON p.id=s.plan_id WHERE s.account_id=%s",
            (account_id,),
        ).fetchone()
    plan = (row or {}).get("code")
    return ("user", plan) if plan in SERVER_CATEGORIES["plan"] else (None, None)


def build_relay_payload(event: dict[str, Any], audience: str | None, plan: str | None) -> dict[str, Any] | None:
    """The PostHog payload for one native event, or None when it must not be sent."""
    name = event.get("event")
    allowed = USER_EVENTS if audience == "user" else OWNER_EVENTS if audience == "owner" else frozenset()
    install_id = str(event.get("install_id") or "").lower()
    if name not in allowed or not UUID.match(install_id):
        return None
    platform = event.get("platform")
    if platform not in SERVER_CATEGORIES["platform"]:
        return None
    environment = analytics_environment() if event.get("build") == "release" else "development"
    properties: dict[str, Any] = {
        **safe_client_properties(event.get("properties")),
        "audience": audience,
        "client": "native",
        "platform": platform,
        "environment": environment,
        "$process_person_profile": False,
        "$geoip_disable": True,
    }
    if audience == "user":
        properties["plan"] = plan
    version = event.get("app_version")
    if isinstance(version, str) and APP_VERSION.match(version):
        properties["app_version"] = version
    session_id = str(event.get("session_id") or "").lower()
    if UUID.match(session_id):
        properties["$session_id"] = session_id
    return {"event": name, "distinct_id": install_id, "properties": properties}


def relay_event(event: dict[str, Any]) -> dict[str, str]:
    """Validate one native event and queue it for PostHog. The answer never reveals the outcome."""
    user = get_current_user()
    if not is_configured():
        return {"status": "accepted"}
    audience, plan = audience_of(user)
    payload = build_relay_payload(event, audience, plan)
    if payload is not None:
        capture_prepared_later(payload)
    return {"status": "accepted"}
