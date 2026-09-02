from __future__ import annotations

from fastapi import APIRouter, Header, Query

from backend.email_monitor.models import EmailCandidateBulkDecisionRequest, EmailCandidateClassifyRequest, EmailCandidateDecisionRequest, EmailStatementReconcileRequest, EmailTextScanRequest
from backend.email_monitor.statement_reconciliation import reconcile_statement
from backend.auth.current_user import get_current_user_id
from backend.core.database import get_connection
from backend.email_monitor.service import (
    cron_sync,
    _workspace_id_for_user,
    bulk_decide_candidates,
    classify_candidate,
    decide_candidate,
    get_email_monitor_status,
    list_email_candidates,
    process_gmail_push,
    renew_gmail_watch,
    scan_email_text,
    sync_gmail_for_owner,
)

router = APIRouter(prefix="/email-monitor", tags=["Email Monitor"])


@router.post("/statements/reconcile")
def email_monitor_statement_reconcile(request: EmailStatementReconcileRequest):
    user_id = get_current_user_id()
    with get_connection() as conn:
        workspace_id = _workspace_id_for_user(conn, user_id)
        result = reconcile_statement(conn, user_id=user_id, workspace_id=workspace_id, statement_id=request.statement_id)
        conn.commit()
        return result


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


@router.post("/candidates/classify")
def email_monitor_candidate_classify(request: EmailCandidateClassifyRequest):
    return classify_candidate(
        candidate_id=request.candidate_id,
        description=request.description,
        transaction_type=request.transaction_type,
        category=request.category,
        remember_rule=request.remember_rule,
        auto_commit_future=request.auto_commit_future,
    )


@router.post("/candidates/bulk-decision")
def email_monitor_candidate_bulk_decision(request: EmailCandidateBulkDecisionRequest):
    return bulk_decide_candidates(candidate_ids=request.candidate_ids, decision=request.decision)


@router.post("/sync-gmail")
def email_monitor_sync_gmail(max_results: int = 150, auto_commit: bool = False, query: str | None = None, current_month_only: bool = True):
    return sync_gmail_for_owner(
        max_results=max_results,
        auto_commit=auto_commit,
        query=query,
        current_month_only=current_month_only,
    )


@router.post("/cron")
def email_monitor_cron(
    x_jarvis_cron_secret: str | None = Header(default=None),
    max_results: int = Query(default=150, ge=1, le=500),
):
    return cron_sync(secret=x_jarvis_cron_secret, max_results=max_results)


@router.post("/gmail-watch")
def email_monitor_gmail_watch(x_jarvis_cron_secret: str | None = Header(default=None)):
    return renew_gmail_watch(secret=x_jarvis_cron_secret)


@router.post("/gmail-push")
def email_monitor_gmail_push(payload: dict, token: str | None = Query(default=None)):
    return process_gmail_push(payload=payload, token=token)
