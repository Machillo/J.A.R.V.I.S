from __future__ import annotations

import json
import os
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

try:
    from pywebpush import WebPushException, webpush
except Exception:  # pragma: no cover - keeps backend alive if dependency is not installed yet.
    WebPushException = Exception
    webpush = None

from backend.auth.current_user import get_current_user, get_current_user_id, get_current_workspace_id
from backend.core.database import get_connection

VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "").strip()
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "").strip()
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:admin@example.invalid").strip()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json(data: Any) -> str:
    return json.dumps(data or {}, ensure_ascii=False)


def _display_name(user: dict[str, Any] | None = None) -> str:
    user = user or get_current_user()
    email = str(user.get("email") or "")
    user_id = int(user.get("id") or 0)

    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT name
                FROM users
                WHERE allowed_user_id = %s OR email = %s OR id = %s
                ORDER BY allowed_user_id NULLS LAST
                LIMIT 1
                """,
                (user_id, email, user_id),
            ).fetchone()
        if row and row.get("name"):
            return str(row["name"]).split()[0].title()
    except Exception:
        pass

    if email:
        return email.split("@", 1)[0].split(".", 1)[0].title()
    return "Kenneth"


def _normalize_subscription_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Accepts either a native PushSubscription JSON or the old local-browser payload.
    """
    raw = payload.get("subscription") if isinstance(payload.get("subscription"), dict) else payload
    endpoint = raw.get("endpoint") or payload.get("endpoint")
    keys = raw.get("keys") or payload.get("keys") or {}
    return {
        "endpoint": endpoint,
        "keys": keys,
        "expirationTime": raw.get("expirationTime"),
        "userAgent": payload.get("userAgent"),
        "device": payload.get("device") or "browser",
        "permission": payload.get("permission") or "granted",
        "raw": raw,
    }


def ensure_notification_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_subscriptions (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES allowed_users(id) ON DELETE CASCADE,
            channel TEXT NOT NULL DEFAULT 'browser',
            endpoint TEXT,
            payload JSONB,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            last_success_at TIMESTAMPTZ,
            last_error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(workspace_id, channel, endpoint)
        )
        """
    )
    conn.execute("ALTER TABLE notification_subscriptions ADD COLUMN IF NOT EXISTS last_success_at TIMESTAMPTZ")
    conn.execute("ALTER TABLE notification_subscriptions ADD COLUMN IF NOT EXISTS last_error TEXT")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS notification_jobs (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES allowed_users(id) ON DELETE CASCADE,
            workspace_id UUID,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'general',
            scheduled_at TIMESTAMPTZ NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            reference_type TEXT,
            reference_id TEXT,
            dedupe_key TEXT,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            sent_at TIMESTAMPTZ,
            last_error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(workspace_id, dedupe_key)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notification_jobs_due ON notification_jobs(status, scheduled_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_notification_jobs_user ON notification_jobs(user_id, scheduled_at)")


def notification_health() -> dict[str, Any]:
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        ensure_notification_tables(conn)
        subscription_count = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM notification_subscriptions
            WHERE workspace_id = %s AND enabled = TRUE
            """,
            (workspace_id,),
        ).fetchone()["total"]
        pending_count = conn.execute(
            """
            SELECT COUNT(*) AS total
            FROM notification_jobs
            WHERE workspace_id = %s AND status = 'pending'
            """,
            (workspace_id,),
        ).fetchone()["total"]
        conn.commit()

    return {
        "status": "OK",
        "vapid_ready": bool(VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY),
        "public_key": VAPID_PUBLIC_KEY,
        "subscriptions": int(subscription_count or 0),
        "pending_jobs": int(pending_count or 0),
        "message": "Web Push listo." if VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY else "Faltan VAPID_PUBLIC_KEY y VAPID_PRIVATE_KEY en Render.",
    }


def get_vapid_public_key() -> dict[str, Any]:
    return {
        "status": "OK" if VAPID_PUBLIC_KEY else "MISSING_KEY",
        "public_key": VAPID_PUBLIC_KEY,
        "message": "Clave pública VAPID lista." if VAPID_PUBLIC_KEY else "Falta VAPID_PUBLIC_KEY en Render.",
    }


def save_push_subscription(payload: dict[str, Any]) -> dict[str, Any]:
    user_id = get_current_user_id()
    workspace_id = get_current_workspace_id()
    normalized = _normalize_subscription_payload(payload)
    endpoint = normalized.get("endpoint")

    if not endpoint:
        return {"status": "ERROR", "message": "No recibí endpoint PushSubscription del navegador."}

    with get_connection() as conn:
        ensure_notification_tables(conn)
        conn.execute(
            """
            INSERT INTO notification_subscriptions (user_id, workspace_id, channel, endpoint, payload, enabled)
            VALUES (%s, %s, 'browser', %s, %s::jsonb, TRUE)
            ON CONFLICT (workspace_id, channel, endpoint)
            DO UPDATE SET payload = EXCLUDED.payload, enabled = TRUE, last_error = NULL, updated_at = NOW()
            """,
            (user_id, workspace_id, endpoint, _json(normalized)),
        )
        conn.commit()

    return {"status": "OK", "message": "Señor, este dispositivo quedó registrado para notificaciones."}


def _push_payload(title: str, body: str, category: str = "general", url: str = "/") -> str:
    return _json({
        "title": title,
        "body": body,
        "category": category,
        "url": url,
        "icon": "/jarvis-icon-192.png",
        "badge": "/jarvis-icon-192.png",
    })


def _send_to_subscription(conn, subscription: dict[str, Any], title: str, body: str, category: str = "general") -> tuple[bool, str | None]:
    if webpush is None:
        return False, "pywebpush no está instalado. Ejecutá requirements.txt actualizado en Render."
    if not (VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY):
        return False, "Faltan VAPID_PUBLIC_KEY/VAPID_PRIVATE_KEY."

    payload = subscription.get("payload") or {}
    raw = payload.get("raw") or payload
    endpoint = subscription.get("endpoint") or raw.get("endpoint")
    keys = raw.get("keys") or payload.get("keys") or {}

    if not endpoint or not keys.get("p256dh") or not keys.get("auth"):
        return False, "Suscripción incompleta: faltan endpoint/p256dh/auth."

    try:
        webpush(
            subscription_info={"endpoint": endpoint, "keys": keys},
            data=_push_payload(title, body, category),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={"sub": VAPID_SUBJECT},
            timeout=15,
        )
        conn.execute(
            """
            UPDATE notification_subscriptions
            SET last_success_at = NOW(), last_error = NULL, updated_at = NOW()
            WHERE id = %s
            """,
            (subscription["id"],),
        )
        return True, None
    except WebPushException as exc:
        message = str(exc)
        conn.execute(
            """
            UPDATE notification_subscriptions
            SET last_error = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (message[:500], subscription["id"]),
        )
        if "410" in message or "404" in message:
            conn.execute(
                """
                UPDATE notification_subscriptions
                SET enabled = FALSE, updated_at = NOW()
                WHERE id = %s
                """,
                (subscription["id"],),
            )
        return False, message
    except Exception as exc:
        message = str(exc)
        conn.execute(
            """
            UPDATE notification_subscriptions
            SET last_error = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (message[:500], subscription["id"]),
        )
        return False, message


def send_system_push(title: str, body: str, category: str = "system", url: str = "/") -> dict[str, Any]:
    """Envía una alerta inmediata a todos los dispositivos owner habilitados."""
    sent = 0
    with get_connection() as conn:
        ensure_notification_tables(conn)
        subscriptions = conn.execute(
            "SELECT * FROM notification_subscriptions WHERE enabled = TRUE"
        ).fetchall()
        for subscription in subscriptions:
            ok, _ = _send_to_subscription(conn, subscription, title, body, category)
            sent += int(ok)
        conn.commit()
    return {"status": "OK", "sent": sent, "url": url}


def send_test_notification() -> dict[str, Any]:
    user = get_current_user()
    user_id = int(user["id"])
    workspace_id = get_current_workspace_id()
    title = "J.A.R.V.I.S."
    body = "Señor, notificaciones reales activadas en este dispositivo."

    with get_connection() as conn:
        ensure_notification_tables(conn)
        subscriptions = conn.execute(
            """
            SELECT *
            FROM notification_subscriptions
            WHERE workspace_id = %s AND enabled = TRUE
            ORDER BY updated_at DESC
            """,
            (workspace_id,),
        ).fetchall()
        sent = 0
        errors: list[str] = []
        for subscription in subscriptions:
            ok, error = _send_to_subscription(conn, subscription, title, body, "test")
            sent += 1 if ok else 0
            if error:
                errors.append(error[:160])
        conn.commit()

    return {
        "status": "OK" if sent else "ERROR",
        "sent": sent,
        "subscriptions": len(subscriptions),
        "errors": errors[:3],
        "message": "Se envió una notificación de prueba." if sent else "No se pudo enviar. Revisá VAPID y permisos del dispositivo.",
    }


def _workspace_id_for_legacy_user(conn, user_id: int) -> str:
    row = conn.execute(
        """
        SELECT w.id
        FROM accounts a
        JOIN workspaces w ON w.owner_account_id = a.id AND w.workspace_type = 'personal'
        WHERE a.legacy_allowed_user_id = %s
        ORDER BY w.created_at, w.id
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()
    if not row:
        raise RuntimeError(f"No workspace personal found for legacy user_id={user_id}.")
    return str(row["id"])


def create_notification_job(
    user_id: int,
    title: str,
    body: str,
    scheduled_at: datetime,
    category: str = "general",
    reference_type: str | None = None,
    reference_id: str | None = None,
    dedupe_key: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    with get_connection() as conn:
        ensure_notification_tables(conn)
        workspace_id = _workspace_id_for_legacy_user(conn, user_id)
        conn.execute(
            """
            INSERT INTO notification_jobs (
                user_id, workspace_id, title, body, category, scheduled_at,
                reference_type, reference_id, dedupe_key, payload
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (workspace_id, dedupe_key)
            DO NOTHING
            """,
            (user_id, workspace_id, title, body, category, scheduled_at, reference_type, reference_id, dedupe_key or f"manual:{workspace_id}:{scheduled_at.isoformat()}:{title}", _json(payload or {})),
        )
        conn.commit()


def _parse_event_datetime(event_date: str | None) -> datetime | None:
    if not event_date:
        return None
    text = str(event_date).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            parsed = datetime.strptime(text[:16] if fmt == "%Y-%m-%d %H:%M" else text[:19] if "T" in fmt else text[:10], fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except Exception:
            continue
    return None


def enqueue_calendar_reminders(days: int = 45) -> int:
    today = _now()
    limit = today + timedelta(days=days)
    created = 0

    with get_connection() as conn:
        ensure_notification_tables(conn)
        rows = conn.execute(
            """
            SELECT e.*, au.email
            FROM events e
            JOIN allowed_users au ON au.id = e.user_id
            WHERE NULLIF(TRIM(e.event_date::text), '') IS NOT NULL
              AND TRIM(e.event_date::text) ~ '^\\d{4}-\\d{2}-\\d{2}'
            ORDER BY e.event_date ASC
            """
        ).fetchall()

        for event in rows:
            event_dt = _parse_event_datetime(event.get("event_date"))
            if not event_dt or event_dt < today or event_dt > limit:
                continue
            user_id = int(event["user_id"])
            title = str(event.get("title") or "Compromiso")
            for label, delta in (("mañana", timedelta(days=1)), ("30min", timedelta(minutes=30))):
                scheduled = event_dt - delta
                if scheduled <= today:
                    continue
                body = f"Señor, {title} está programado para {event.get('event_date')}."
                if label == "30min":
                    body = f"Señor, {title} inicia en 30 minutos."
                before_count = conn.execute(
                    """
                    INSERT INTO notification_jobs (user_id, workspace_id, title, body, category, scheduled_at, reference_type, reference_id, dedupe_key, payload)
                    VALUES (%s, %s, %s, %s, 'calendar', %s, 'event', %s, %s, %s::jsonb)
                    ON CONFLICT (workspace_id, dedupe_key) DO NOTHING
                    RETURNING id
                    """,
                    (
                        user_id,
                        str(event["workspace_id"]),
                        "Recordatorio de calendario",
                        body,
                        scheduled,
                        str(event.get("id")),
                        f"calendar:{event.get('id')}:{label}",
                        _json({"event": event}),
                    ),
                ).fetchone()
                if before_count:
                    created += 1
        conn.commit()
    return created


def enqueue_fixed_expense_reminders() -> int:
    today = date.today()
    created = 0
    month_keys = [f"{today.year:04d}-{today.month:02d}"]
    next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_keys.append(f"{next_month.year:04d}-{next_month.month:02d}")

    with get_connection() as conn:
        ensure_notification_tables(conn)
        expenses = conn.execute(
            """
            SELECT fe.*, au.email
            FROM fixed_expenses fe
            JOIN allowed_users au ON au.id = fe.user_id
            WHERE fe.is_active = TRUE AND fe.due_day IS NOT NULL
            """
        ).fetchall()
        for expense in expenses:
            due_day = int(expense.get("due_day") or 1)
            reminder_days = int(expense.get("reminder_days") or 3)
            for month_key in month_keys:
                year, month = [int(part) for part in month_key.split("-", 1)]
                safe_day = min(max(due_day, 1), monthrange(year, month)[1])
                due = datetime.combine(date(year, month, safe_day), time(9, 0), tzinfo=timezone.utc)
                for label, scheduled in (("before", due - timedelta(days=reminder_days)), ("due", due)):
                    if scheduled.date() < today:
                        continue
                    amount = expense.get("expected_amount")
                    amount_text = f" por ₡{float(amount):,.0f}".replace(",", ".") if amount else ""
                    body = f"Señor, {expense.get('name')} vence el {due.date().isoformat()}{amount_text}."
                    row = conn.execute(
                        """
                        INSERT INTO notification_jobs (user_id, workspace_id, title, body, category, scheduled_at, reference_type, reference_id, dedupe_key, payload)
                        VALUES (%s, %s, %s, %s, 'fixed_expense', %s, 'fixed_expense', %s, %s, %s::jsonb)
                        ON CONFLICT (workspace_id, dedupe_key) DO NOTHING
                        RETURNING id
                        """,
                        (
                            int(expense["user_id"]),
                            "Pago recurrente",
                            body,
                            scheduled,
                            str(expense.get("id")),
                            f"fixed:{expense.get('id')}:{month_key}:{label}",
                            _json({"fixed_expense": expense, "due_date": due.date().isoformat()}),
                        ),
                    ).fetchone()
                    if row:
                        created += 1
        conn.commit()
    return created


def send_due_notifications(limit: int = 50) -> dict[str, Any]:
    queued_calendar = enqueue_calendar_reminders()
    queued_fixed = enqueue_fixed_expense_reminders()
    try:
        from backend.sports.service import enqueue_owner_sports_digest_notifications
        queued_sports = enqueue_owner_sports_digest_notifications()
    except Exception as exc:
        queued_sports = {"status": "ERROR", "message": str(exc)}

    with get_connection() as conn:
        ensure_notification_tables(conn)
        jobs = conn.execute(
            """
            SELECT *
            FROM notification_jobs
            WHERE status = 'pending' AND scheduled_at <= NOW()
            ORDER BY scheduled_at ASC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()

        sent_jobs = 0
        failed_jobs = 0
        for job in jobs:
            subscriptions = conn.execute(
                """
                SELECT *
                FROM notification_subscriptions
                WHERE workspace_id = %s AND enabled = TRUE
                """,
                (job["workspace_id"],),
            ).fetchall()
            sent_to = 0
            errors: list[str] = []
            for subscription in subscriptions:
                ok, error = _send_to_subscription(conn, subscription, job["title"], job["body"], job["category"])
                sent_to += 1 if ok else 0
                if error:
                    errors.append(error[:160])
            if sent_to:
                conn.execute(
                    """
                    UPDATE notification_jobs
                    SET status = 'sent', sent_at = NOW(), last_error = NULL, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (job["id"],),
                )
                sent_jobs += 1
            else:
                conn.execute(
                    """
                    UPDATE notification_jobs
                    SET status = 'failed', last_error = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (("; ".join(errors) or "No hay suscripciones activas")[:500], job["id"]),
                )
                failed_jobs += 1
        conn.commit()

    return {
        "status": "OK",
        "queued_calendar": queued_calendar,
        "queued_fixed_expenses": queued_fixed,
        "queued_sports": queued_sports,
        "due_jobs": len(jobs),
        "sent_jobs": sent_jobs,
        "failed_jobs": failed_jobs,
    }
