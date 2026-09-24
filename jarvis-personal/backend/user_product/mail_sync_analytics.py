"""Anonymous health events for every mailbox sync (Gmail and Outlook).

Covers all triggers, including the ones with no app on screen (maintenance cron,
provider push, the first sync after connecting). Only the provider, the trigger,
the outcome, the duration and message counts are reported. Never the mailbox,
the account, a message, a sender, a subject or anything extracted from it.
"""
from __future__ import annotations

from time import monotonic
from typing import Any, Callable

from fastapi import HTTPException

from backend.product_ops.posthog_events import capture_backend_event_later


def _error_code(exc: BaseException) -> str:
    if isinstance(exc, HTTPException):
        if exc.status_code == 409:
            return "reauth_required"
        if exc.status_code == 403:
            return "access_denied"
    return "provider_error"


def observe_mail_sync(provider: str, trigger: str, run: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Run one mailbox sync and report its outcome; the result and errors pass through unchanged."""
    started = monotonic()
    try:
        result = run()
    except BaseException as exc:
        capture_backend_event_later("mail_sync_failed", {
            "provider": provider, "trigger": trigger, "error_code": _error_code(exc),
            "duration_ms": (monotonic() - started) * 1000,
        })
        raise
    capture_backend_event_later("mail_sync_completed", {
        "provider": provider, "trigger": trigger,
        "scan_scope": result.get("scan_scope"),
        "initial_scan_complete": result.get("initial_scan_complete"),
        "duration_ms": (monotonic() - started) * 1000,
        "messages_scanned": result.get("found"),
        "candidates_pending": result.get("pending"),
        "duplicates": result.get("duplicates"),
        "payroll_reports": result.get("payroll_reports"),
    })
    return result
