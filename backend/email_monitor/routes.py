from __future__ import annotations

from fastapi import APIRouter, Header, Query

from backend.email_monitor.models import EmailCandidateDecisionRequest, EmailTextScanRequest
from backend.email_monitor.service import (
    cron_sync,
    decide_candidate,
    get_email_monitor_status,
    list_email_candidates,
    scan_email_text,
    sync_gmail_for_owner,
)

router = APIRouter(prefix="/email-monitor", tags=["Email Monitor"])


@router.get("/status")
def email_monitor_status():
    return get_email_monitor_status()


@router.post("/scan-text")
def email_monitor_scan_text(request: EmailTextScanRequest):
    return scan_email_text(
        subject=request.subject,
        sender=request.sender,
        body=request.body,
        received_at=request.received_at,
        auto_commit=request.auto_commit,
    )


@router.get("/candidates")
def email_monitor_candidates(status: str | None = None, limit: int = 50):
    return list_email_candidates(status_filter=status, limit=limit)


@router.post("/candidates/decision")
def email_monitor_candidate_decision(request: EmailCandidateDecisionRequest):
    return decide_candidate(candidate_id=request.candidate_id, decision=request.decision)


@router.post("/sync-gmail")
def email_monitor_sync_gmail(max_results: int = 10, auto_commit: bool = False, query: str | None = None, current_month_only: bool = True):
    return sync_gmail_for_owner(
        max_results=max_results,
        auto_commit=auto_commit,
        query=query,
        current_month_only=current_month_only,
    )


@router.post("/cron")
def email_monitor_cron(
    x_jarvis_cron_secret: str | None = Header(default=None),
    max_results: int = Query(default=20, ge=1, le=100),
):
    return cron_sync(secret=x_jarvis_cron_secret, max_results=max_results)
