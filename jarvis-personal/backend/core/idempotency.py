import hashlib
import json
import logging
import re
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from backend.core.database import get_connection


logger = logging.getLogger("finva.idempotency")

IDEMPOTENCY_KEY_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
RECOVERABLE_METHODS = {"POST", "PUT", "PATCH"}
RECOVERABLE_PATH_PATTERN = re.compile(
    r"^/user-product/(?:"
    r"financial-situation|"
    r"finance/(?:income|expenses|debts)(?:/[^/]+(?:/payments)?)?|"
    r"goals(?:/[^/]+(?:/contributions)?)?|"
    r"savings-plans(?:/[^/]+(?:/contributions)?)?|"
    r"transactions|"
    r"basic/(?:budget|recurring(?:/[^/]+)?)"
    r")/?$"
)


@dataclass(frozen=True)
class Reservation:
    state: str
    response_status: int | None = None
    response_body: Any = None
    # updated_at written by this reservation (clock_timestamp()); identifies the attempt.
    lease: Any = None


@dataclass(frozen=True)
class ActiveOperation:
    account_id: str
    key: str
    lease: Any


class OperationSuperseded(Exception):
    """A newer attempt re-reserved this key; this attempt must not apply its write."""


# Set by the HTTP middleware only while a reserved recoverable request runs its handler.
_active_operation: ContextVar[ActiveOperation | None] = ContextVar("active_idempotent_operation", default=None)

ALREADY_APPLIED_BODY = {"status": "already_applied"}


def activate_operation(*, account_id: str, key: str, lease: Any):
    return _active_operation.set(ActiveOperation(account_id, key, lease))


def deactivate_operation(token) -> None:
    _active_operation.reset(token)


def mark_applied(conn) -> None:
    """Bind the active idempotent operation to the caller's business transaction.

    Call inside the transaction that performs the financial write, right before its
    commit. The reservation turns 'completed' atomically with the write, so a retry
    after a crash can never apply it twice. If a newer attempt re-reserved the key
    (stale lease), raise so the caller's write is rolled back. No-op outside a
    reserved recoverable request.
    """
    operation = _active_operation.get()
    if operation is None:
        return
    row = conn.execute(
        """UPDATE operation_idempotency
           SET status='completed'
           WHERE account_id=%s AND idempotency_key=%s
             AND status='processing' AND updated_at=%s::timestamptz
           RETURNING idempotency_key""",
        (operation.account_id, operation.key, operation.lease),
    ).fetchone()
    if not row:
        raise OperationSuperseded()


def is_recoverable_operation(method: str, path: str) -> bool:
    return method.upper() in RECOVERABLE_METHODS and bool(RECOVERABLE_PATH_PATTERN.fullmatch(path))


def request_hash(method: str, path: str, body: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(method.upper().encode("utf-8"))
    digest.update(b"\0")
    digest.update(path.encode("utf-8"))
    digest.update(b"\0")
    digest.update(body)
    return digest.hexdigest()


def reserve_operation(*, account_id: str, key: str, method: str, path: str, digest: str) -> Reservation:
    """Reserve one write or return its prior response without logging its payload."""
    with get_connection() as conn:
        inserted = conn.execute(
            """INSERT INTO operation_idempotency(
                 account_id,idempotency_key,request_hash,method,path,updated_at
               ) VALUES(%s,%s,%s,%s,%s,clock_timestamp())
               ON CONFLICT(account_id,idempotency_key) DO NOTHING
               RETURNING updated_at""",
            (account_id, key, digest, method.upper(), path),
        ).fetchone()
        if inserted:
            conn.commit()
            return Reservation("reserved", lease=inserted["updated_at"])

        row = conn.execute(
            """SELECT request_hash,status,response_status,response_body,
                      updated_at < NOW()-INTERVAL '2 minutes' AS stale,
                      expires_at <= NOW() AS expired
               FROM operation_idempotency
               WHERE account_id=%s AND idempotency_key=%s
               FOR UPDATE""",
            (account_id, key),
        ).fetchone()
        if not row:
            conn.rollback()
            return Reservation("unavailable")
        if row["request_hash"] != digest:
            conn.rollback()
            return Reservation("conflict")
        if row["status"] == "completed" and not row["expired"]:
            conn.commit()
            if row["response_status"] is None and row.get("response_body") is None:
                # The write committed with mark_applied but its response was never stored.
                return Reservation("replay", 200, dict(ALREADY_APPLIED_BODY))
            return Reservation(
                "replay",
                int(row["response_status"] or 200),
                row.get("response_body"),
            )
        if row["status"] == "processing" and not row["stale"]:
            conn.commit()
            return Reservation("processing")

        # Stale 'processing' (attempt presumed dead) or expired record: start a new
        # attempt with a new lease. A slow previous attempt now loses in mark_applied.
        renewed = conn.execute(
            """UPDATE operation_idempotency
               SET status='processing',response_status=NULL,response_body=NULL,
                   updated_at=clock_timestamp(),expires_at=NOW()+INTERVAL '24 hours'
               WHERE account_id=%s AND idempotency_key=%s
               RETURNING updated_at""",
            (account_id, key),
        ).fetchone()
        conn.commit()
        return Reservation("reserved", lease=renewed["updated_at"])


def complete_operation(*, account_id: str, key: str, lease: Any, status_code: int, body: bytes) -> None:
    """Store the response of this attempt, if it still owns the key.

    A response that cannot be stored (>64KB, non-JSON) releases a still 'processing'
    reservation; a write already bound with mark_applied stays 'completed' and later
    retries replay {"status": "already_applied"}.
    """
    if len(body) > 64 * 1024:
        abandon_operation(account_id=account_id, key=key, lease=lease)
        return
    try:
        payload = json.loads(body.decode("utf-8")) if body else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        abandon_operation(account_id=account_id, key=key, lease=lease)
        return
    with get_connection() as conn:
        conn.execute(
            """UPDATE operation_idempotency
               SET status='completed',response_status=%s,response_body=%s::jsonb,
                   updated_at=NOW(),expires_at=NOW()+INTERVAL '24 hours'
               WHERE account_id=%s AND idempotency_key=%s
                 AND updated_at=%s::timestamptz AND status IN ('processing','completed')""",
            (status_code, json.dumps(payload), account_id, key, lease),
        )
        conn.commit()


def abandon_operation(*, account_id: str, key: str, lease: Any) -> None:
    """Release this attempt's reservation unless its write was already applied."""
    with get_connection() as conn:
        conn.execute(
            """DELETE FROM operation_idempotency
               WHERE account_id=%s AND idempotency_key=%s
                 AND status='processing' AND updated_at=%s::timestamptz""",
            (account_id, key, lease),
        )
        conn.commit()


def safe_abandon_operation(*, account_id: str, key: str, lease: Any) -> None:
    try:
        abandon_operation(account_id=account_id, key=key, lease=lease)
    except Exception:
        logger.exception("Could not release idempotency reservation account_id=%s", account_id)
