"""Liveness, readiness and the Owner-only operational view.

- ``GET /health/live``: the process answers. No dependency is touched, so a
  platform health check never restarts DINCR because the database blinked.
- ``GET /health/ready``: DINCR can serve requests (the database answers).
  ``healthy`` | ``degraded`` (serving, with open server-side incidents) 200, or
  ``unhealthy`` 503. Public and minimal: no hosts, DSNs, versions or errors.
  The probe result is shared for READY_TTL_SECONDS (success or failure), so a
  flood of probes cannot become a flood of database connections.
- ``GET /product-ops/owner/observability``: Owner only; incidents, job
  heartbeats, alert configuration (never the webhook) and connection counters.
"""
from __future__ import annotations

import threading
import time

import psycopg2
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.auth.current_user import require_roles
from backend.core import database, observability as ops
from backend.core.schema_state import tables_exist

router = APIRouter(tags=["Health"])

READY_TTL_SECONDS = 10
DB_CONNECT_TIMEOUT_SECONDS = 3
_probe_lock = threading.Lock()
_probe: dict = {"at": None, "ok": None}


def _database_answers() -> bool:
    """A dedicated short-timeout connection: the request pool is never involved."""
    started = time.monotonic()
    try:
        connection = psycopg2.connect(
            database.DATABASE_URL, connect_timeout=DB_CONNECT_TIMEOUT_SECONDS, application_name="dincr-readiness",
            keepalives=1, keepalives_idle=5, keepalives_interval=2, keepalives_count=2,
        )
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = 2000")  # transaction-scoped: safe with Supavisor
                cursor.execute("SELECT 1")
                cursor.fetchone()
        finally:
            connection.close()
    except Exception as exc:
        ops.report("database", "unreachable", "critical", error_class=type(exc).__name__,
                   error_code=getattr(exc, "pgcode", None), duration_ms=int((time.monotonic() - started) * 1000))
        return False
    # Only the probe's own incident: pool connect failures recover when they go quiet,
    # so a flapping pool cannot turn every probe into a new CRITICAL page.
    ops.recovered("database", "unreachable")
    return True


def database_ready() -> bool:
    """The last probe result; at most one probe runs, and nobody waits for it."""
    fresh = _probe["at"] is not None and time.monotonic() - _probe["at"] < READY_TTL_SECONDS
    if fresh or not _probe_lock.acquire(blocking=False):
        # Fresh, or another request is probing right now: answer from the last result
        # (healthy until the first probe finishes) instead of holding a worker thread.
        return _probe["ok"] is not False
    try:
        _probe["ok"], _probe["at"] = _database_answers(), time.monotonic()
        return bool(_probe["ok"])
    finally:
        _probe_lock.release()


# Shorter than the recovery quiet period (15 min), so a job that stays stale keeps
# its incident open instead of flapping between RECOVERED and a new alert.
JOB_CHECK_SECONDS = 600
_jobs_lock = threading.Lock()
_jobs_checked: dict = {"at": None}


def _stale_jobs() -> None:
    """Background work that stopped, read from state DINCR already keeps (no new tables).

    - Mail: active mailboxes exist but none synced for OPS_MAIL_SYNC_STALE_HOURS
      (maintenance/push not running, or failing everywhere).
    - Notifications: jobs stuck in 'sending'/'retry' for more than an hour.
    Aggregates only: counts and ages, never an account or a mailbox.
    """
    stale_hours = ops._int_env("OPS_MAIL_SYNC_STALE_HOURS", 24)
    with database.get_connection() as conn:
        present = {name for name in ("finva_gmail_connections", "notification_jobs") if tables_exist(conn, [name])}
        if "finva_gmail_connections" in present:
            row = conn.execute(
                """SELECT COUNT(*) AS active,
                          COUNT(*) FILTER (WHERE last_success_at >= NOW() - make_interval(hours => %s)) AS recent
                   FROM finva_gmail_connections WHERE status='active'""", (stale_hours,),
            ).fetchone() or {}
            if int(row.get("active") or 0) and not int(row.get("recent") or 0):
                ops.report("job", "mail_sync_stale", "error", error_code=f"none_in_{stale_hours}h")
            else:
                ops.recovered("job", "mail_sync_stale")
        if "notification_jobs" in present:
            stuck = conn.execute(
                """SELECT COUNT(*) AS stuck FROM notification_jobs
                   WHERE status IN ('sending','retry') AND updated_at < NOW() - INTERVAL '1 hour'"""
            ).fetchone() or {}
            if int(stuck.get("stuck") or 0):
                ops.report("job", "notifications_stuck", "warning", error_code="over_1h")
            else:
                ops.recovered("job", "notifications_stuck")
        conn.commit()


def check_jobs() -> None:
    if not _jobs_lock.acquire(blocking=False):
        return  # another probe is checking
    try:
        if _jobs_checked["at"] is not None and time.monotonic() - _jobs_checked["at"] < JOB_CHECK_SECONDS:
            return
        _jobs_checked["at"] = time.monotonic()
        _stale_jobs()
    except Exception as exc:
        ops.report("observability", "job_check_failed", "warning", error_class=type(exc).__name__)
    finally:
        _jobs_lock.release()


def readiness() -> tuple[int, dict]:
    ops.sweep()  # quiet incidents turn into RECOVERED even when nothing else happens
    database_ok = database_ready()
    if database_ok:
        check_jobs()
    # Public "degraded": only what serves every user (API, database, auth). Jobs,
    # integrations and deploys stay in the Owner view and alerts.
    open_errors = any(row["severity"] in {"error", "critical"} and row["component"] in {"api", "database", "auth"}
                      for row in ops.GATE.snapshot())
    status = "unhealthy" if not database_ok else "degraded" if open_errors else "healthy"
    return (503 if status == "unhealthy" else 200), {"status": status, "checks": {"database": "ok" if database_ok else "fail"}}


@router.get("/health/live")
async def live():  # on the event loop: never waits for the thread pool
    return {"status": "alive"}


@router.get("/health/ready")
def ready():
    status_code, body = readiness()
    return JSONResponse(status_code=status_code, content=body)


@router.get("/product-ops/owner/observability")
def owner_observability():
    require_roles("owner")
    status_code, body = readiness()
    return {**body, "http_status": status_code, **ops.status_snapshot(),
            "database_connections": database.connection_pool_stats()}
