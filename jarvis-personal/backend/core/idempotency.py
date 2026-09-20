import hashlib
import json
import logging
import re
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
                 account_id,idempotency_key,request_hash,method,path
               ) VALUES(%s,%s,%s,%s,%s)
               ON CONFLICT(account_id,idempotency_key) DO NOTHING
               RETURNING idempotency_key""",
            (account_id, key, digest, method.upper(), path),
        ).fetchone()
        if inserted:
            conn.commit()
            return Reservation("reserved")

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
            return Reservation(
                "replay",
                int(row["response_status"] or 200),
                row.get("response_body"),
            )
        if row["status"] == "processing" and not row["stale"]:
            conn.commit()
            return Reservation("processing")

        conn.execute(
            """UPDATE operation_idempotency
               SET status='processing',response_status=NULL,response_body=NULL,
                   updated_at=NOW(),expires_at=NOW()+INTERVAL '24 hours'
               WHERE account_id=%s AND idempotency_key=%s""",
            (account_id, key),
        )
        conn.commit()
        return Reservation("reserved")


def complete_operation(*, account_id: str, key: str, status_code: int, body: bytes) -> None:
    if len(body) > 64 * 1024:
        abandon_operation(account_id=account_id, key=key)
        return
    try:
        payload = json.loads(body.decode("utf-8")) if body else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        abandon_operation(account_id=account_id, key=key)
        return
    with get_connection() as conn:
        conn.execute(
            """UPDATE operation_idempotency
               SET status='completed',response_status=%s,response_body=%s::jsonb,
                   updated_at=NOW(),expires_at=NOW()+INTERVAL '24 hours'
               WHERE account_id=%s AND idempotency_key=%s""",
            (status_code, json.dumps(payload), account_id, key),
        )
        conn.commit()


def abandon_operation(*, account_id: str, key: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM operation_idempotency WHERE account_id=%s AND idempotency_key=%s AND status='processing'",
            (account_id, key),
        )
        conn.commit()


def safe_abandon_operation(*, account_id: str, key: str) -> None:
    try:
        abandon_operation(account_id=account_id, key=key)
    except Exception:
        logger.exception("Could not release idempotency reservation account_id=%s", account_id)
