from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.email_monitor.models import EmailCandidateBulkDecisionRequest, EmailCandidateClassifyRequest, EmailCandidateDecisionRequest, EmailStatementReconcileRequest, EmailTextScanRequest
from backend.email_monitor.statement_reconciliation import reconcile_statement
from backend.auth.current_user import get_current_user_id, require_roles
from backend.core.database import get_connection
from backend.email_monitor.service import (
    _workspace_id_for_user,
    bulk_decide_candidates,
    classify_candidate,
    decide_candidate,
    get_email_monitor_status,
    list_email_candidates,
    scan_email_text,
)

router = APIRouter(prefix="/email-monitor", tags=["Email Monitor"])


@router.post("/statements/reconcile")
def email_monitor_statement_reconcile(request: EmailStatementReconcileRequest):
    require_roles("owner", "admin")
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


# The Owner's legacy Gmail reader (one server-held refresh token, cron, Pub/Sub
# watch) is retired. The Owner connects each mailbox through the standard
# per-account OAuth flow (/user-product/vip/gmail/*), like every DINCR account.
LEGACY_READER_RETIRED = (
    "El lector Gmail legacy fue retirado. Conectá tus correos desde Correos financieros."
)


@router.post("/sync-gmail")
def email_monitor_sync_gmail():
    require_roles("owner")
    raise HTTPException(status_code=410, detail=LEGACY_READER_RETIRED)


@router.post("/sync-ccss-payroll")
def email_monitor_sync_ccss_payroll():
    # CCSS payroll orders now arrive with each connected mailbox sync
    # (payroll_salary_reports); Finance's aguinaldo refresh just reads them.
    require_roles("owner")
    return {"status": "OK", "source": "connected_mailboxes", "message": "Las órdenes patronales llegan con la sincronización de tus correos conectados."}


@router.post("/cron")
def email_monitor_cron():
    raise HTTPException(status_code=410, detail=LEGACY_READER_RETIRED)


@router.post("/gmail-watch")
def email_monitor_gmail_watch():
    raise HTTPException(status_code=410, detail=LEGACY_READER_RETIRED)


@router.post("/gmail-push")
def email_monitor_gmail_push():
    # Acknowledge without processing so a leftover Pub/Sub push subscription stops
    # retrying; nothing is read from Gmail.
    return {"status": "retired"}
