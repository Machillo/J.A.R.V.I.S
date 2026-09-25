import hashlib
import logging
import os
import re
import secrets
import smtplib
import requests
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from email.message import EmailMessage
from types import SimpleNamespace
from urllib.parse import urlsplit

from fastapi import HTTPException

from backend.auth.current_user import get_current_account_id, get_current_user, get_current_workspace_id
from backend.core.database import get_connection
from backend.core.schema_state import tables_exist
from backend.core.feature_flags import FEATURE_DEFINITIONS, clear_feature_flag_cache
from backend.product_ops.email_monitor_dashboard import build_email_monitor_dashboard

LAUNCH_PROMOTION_CODE = "launch-free-2026"
LAUNCH_PROMOTION_END = datetime(2027, 1, 1, 6, 0, 0, tzinfo=timezone.utc)
PRICES = {
    "basic": {"regular": 2990},
    "vip": {"regular": 4990},
}
# Public payments are App Store / Google Play only (store_billing.py). DINCR never
# takes an off-store payment (no SINPE, transfers, receipts or manual orders).
STORE_ENTITLED_STATES = ("trialing", "active", "grace_period")
logger = logging.getLogger(__name__)
RELEASE_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[+-][A-Za-z0-9.-]+)?$")
def _discord_webhook_host(webhook: str) -> str | None:
    """Return the verified official Discord host without exposing webhook secrets."""
    fingerprint = hashlib.sha256(webhook.encode("utf-8", errors="replace")).hexdigest()[:12]
    try:
        parsed = urlsplit(webhook)
        host = (parsed.hostname or "").lower()
        official_host = any(host == domain or host.endswith(f".{domain}") for domain in (
            "discord.com", "discordapp.com",
        ))
        if (
            parsed.scheme.lower() == "https"
            and official_host
            and parsed.port in {None, 443}
            and parsed.username is None
            and parsed.password is None
            and parsed.path.startswith("/api/webhooks/")
        ):
            return host
        logger.error(
            "Discord webhook validation failed scheme=%r host=%r port=%r credentials=%s "
            "path_valid=%s fingerprint=%s length=%s",
            parsed.scheme.lower(), host, parsed.port,
            parsed.username is not None or parsed.password is not None,
            parsed.path.startswith("/api/webhooks/"), fingerprint, len(webhook),
        )
    except (TypeError, ValueError) as error:
        logger.error(
            "Discord webhook validation parse failure type=%s fingerprint=%s length=%s",
            type(error).__name__, fingerprint, len(webhook),
        )
    return None


def _release_version_tuple(value: str | None) -> tuple[int, int, int] | None:
    """Parse the numeric SemVer core used for compatibility decisions."""
    normalized = str(value or "").strip()
    if not RELEASE_VERSION_PATTERN.fullmatch(normalized):
        return None
    core = re.split(r"[+-]", normalized, maxsplit=1)[0]
    return tuple(int(part) for part in core.split("."))


def evaluate_release_version(current: str | None, minimum: str, latest: str) -> str:
    current_tuple = _release_version_tuple(current)
    minimum_tuple = _release_version_tuple(minimum)
    latest_tuple = _release_version_tuple(latest)
    if not current_tuple or not minimum_tuple or not latest_tuple:
        return "unknown"
    if current_tuple < minimum_tuple:
        return "required"
    if current_tuple < latest_tuple:
        return "optional"
    return "current"


def release_policy(platform: str, current_version: str):
    """Return only the public, privacy-safe compatibility decision."""
    if platform not in {"android", "ios", "web"}:
        raise HTTPException(422, "Plataforma no válida.")
    with get_connection() as conn:
        row = conn.execute(
            """SELECT platform,minimum_supported_version,latest_version,update_url,
                      message_es,message_en,is_active,updated_at
               FROM app_release_policies WHERE platform=%s""",
            (platform,),
        ).fetchone()
    if not row or not row.get("is_active"):
        return {"platform": platform, "current_version": current_version, "status": "current", "required": False, "active": False}
    status = evaluate_release_version(current_version, row["minimum_supported_version"], row["latest_version"])
    return {
        **row,
        "current_version": current_version,
        "status": status,
        "required": status == "required",
        "active": True,
    }


def update_release_policy(platform: str, payload):
    if platform not in {"android", "ios", "web"}:
        raise HTTPException(422, "Plataforma no válida.")
    minimum = _release_version_tuple(payload.minimum_supported_version)
    latest = _release_version_tuple(payload.latest_version)
    if not minimum or not latest or latest < minimum:
        raise HTTPException(422, "La versión más reciente debe ser igual o posterior a la versión mínima.")
    if payload.is_active and (minimum > (1, 0, 0) or latest > minimum) and not payload.update_url:
        raise HTTPException(422, "Configurá una URL HTTPS antes de anunciar o exigir una actualización.")
    account_id = get_current_account_id()
    with get_connection() as conn:
        row = conn.execute(
            """INSERT INTO app_release_policies(
                 platform,minimum_supported_version,latest_version,update_url,
                 message_es,message_en,is_active,updated_by_account_id,updated_at
               ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,NOW())
               ON CONFLICT(platform) DO UPDATE SET
                 minimum_supported_version=EXCLUDED.minimum_supported_version,
                 latest_version=EXCLUDED.latest_version,
                 update_url=EXCLUDED.update_url,message_es=EXCLUDED.message_es,
                 message_en=EXCLUDED.message_en,is_active=EXCLUDED.is_active,
                 updated_by_account_id=EXCLUDED.updated_by_account_id,updated_at=NOW()
               RETURNING platform,minimum_supported_version,latest_version,update_url,
                         message_es,message_en,is_active,updated_at""",
            (platform, payload.minimum_supported_version, payload.latest_version,
             payload.update_url, payload.message_es.strip(), payload.message_en.strip(),
             payload.is_active, account_id),
        ).fetchone()
        conn.commit()
    logger.info("Release policy updated platform=%s account_id=%s", platform, account_id)
    return row


def update_feature_flag(flag_key: str, payload):
    if flag_key not in FEATURE_DEFINITIONS:
        raise HTTPException(404, "Interruptor operativo no encontrado.")
    reason = payload.reason.strip()
    if len(reason) < 3:
        raise HTTPException(422, "Indicá el motivo del cambio.")
    account_id = get_current_account_id()
    with get_connection() as conn:
        current = conn.execute(
            "SELECT flag_key,enabled FROM app_feature_flags WHERE flag_key=%s FOR UPDATE",
            (flag_key,),
        ).fetchone()
        if not current:
            raise HTTPException(404, "Interruptor operativo no encontrado.")
        row = conn.execute(
            """UPDATE app_feature_flags SET enabled=%s,updated_by_account_id=%s,updated_at=NOW()
               WHERE flag_key=%s RETURNING flag_key,display_name,description,enabled,
               safe_default_enabled,disabled_message_es,disabled_message_en,updated_at""",
            (payload.enabled, account_id, flag_key),
        ).fetchone()
        conn.execute(
            """INSERT INTO app_feature_flag_audit(
                 flag_key,previous_enabled,new_enabled,reason,changed_by_account_id
               ) VALUES(%s,%s,%s,%s,%s)""",
            (flag_key, current["enabled"], payload.enabled, reason, account_id),
        )
        conn.commit()
    clear_feature_flag_cache()
    logger.warning(
        "Operational feature flag changed flag=%s enabled=%s account_id=%s",
        flag_key, payload.enabled, account_id,
    )
    return row


def support_email_configuration() -> dict[str, object]:
    """Return non-secret SMTP readiness details for the owner dashboard."""
    username = os.getenv("SUPPORT_SMTP_USER", "").strip()
    password = re.sub(r"\s+", "", os.getenv("SUPPORT_SMTP_APP_PASSWORD", ""))
    recipient = os.getenv("SUPPORT_EMAIL_TO", "soporte@dincr.com").strip()
    missing = [name for name, value in (
        ("SUPPORT_SMTP_USER", username),
        ("SUPPORT_SMTP_APP_PASSWORD", password),
        ("SUPPORT_EMAIL_TO", recipient),
    ) if not value]
    return {
        "configured": not missing,
        "missing": missing,
        "recipient": recipient or None,
        "host": os.getenv("SUPPORT_SMTP_HOST", "smtp.gmail.com").strip(),
        "port": int(os.getenv("SUPPORT_SMTP_PORT", "465")),
    }


def support_channel_configuration() -> dict[str, object]:
    minimum = os.getenv("SUPPORT_DISCORD_MIN_SEVERITY", "critical").strip().lower()
    if minimum not in {"info", "warning", "critical"}:
        minimum = "critical"
    return {
        "email": support_email_configuration(),
        "discord_configured": bool(os.getenv("SUPPORT_DISCORD_WEBHOOK_URL", "").strip()),
        "discord_min_severity": minimum,
        "discord_role_configured": bool(re.fullmatch(r"\d{5,30}", os.getenv("SUPPORT_DISCORD_ALERT_ROLE_ID", "").strip())),
    }


def _send_support_email(*, public_id: str, email: str, plan: str, payload) -> bool:
    """Best-effort support notification. The database ticket remains canonical."""
    host = os.getenv("SUPPORT_SMTP_HOST", "smtp.gmail.com").strip()
    port = int(os.getenv("SUPPORT_SMTP_PORT", "465"))
    username = os.getenv("SUPPORT_SMTP_USER", "").strip()
    # Google displays app passwords grouped with spaces. SMTP expects the
    # sixteen characters without whitespace.
    password = re.sub(r"\s+", "", os.getenv("SUPPORT_SMTP_APP_PASSWORD", ""))
    recipient = os.getenv("SUPPORT_EMAIL_TO", "soporte@dincr.com").strip()
    sender = os.getenv("SUPPORT_SMTP_FROM", username).strip() or username
    if not username or not password or not recipient:
        missing = support_email_configuration()["missing"]
        logger.warning("Support email not sent for %s: missing %s", public_id, ", ".join(missing))
        return False

    message = EmailMessage()
    message["Subject"] = f"[{public_id}] {payload.category.upper()}: {payload.subject.strip()}"
    message["From"] = sender
    message["To"] = recipient
    if email and email != "no disponible":
        message["Reply-To"] = email
    message.set_content(
        "\n".join([
            f"Ticket: {public_id}",
            f"Tipo: {payload.category}",
            f"Usuario: {email}",
            f"Plan: {plan or 'desconocido'}",
            f"Versión: {payload.app_version or 'no indicada'}",
            f"Pantalla: {payload.screen or 'no indicada'}",
            f"Referencia del error: {payload.error_reference or 'ninguna'}",
            "",
            payload.message.strip(),
        ])
    )
    ports = [port]
    if host.lower() == "smtp.gmail.com":
        fallback_port = 587 if port == 465 else 465
        ports.append(fallback_port)

    for candidate_port in dict.fromkeys(ports):
        try:
            if candidate_port == 465:
                with smtplib.SMTP_SSL(host, candidate_port, timeout=15) as smtp:
                    smtp.login(username, password)
                    smtp.send_message(message)
            else:
                with smtplib.SMTP(host, candidate_port, timeout=15) as smtp:
                    smtp.ehlo()
                    smtp.starttls()
                    smtp.ehlo()
                    smtp.login(username, password)
                    smtp.send_message(message)
            logger.info("Support email delivered for %s using SMTP port %s", public_id, candidate_port)
            return True
        except smtplib.SMTPAuthenticationError:
            logger.exception(
                "Support email authentication failed for %s. Verify the Google app password and SMTP user.",
                public_id,
            )
            return False
        except Exception:
            logger.exception("Support email delivery failed for %s using SMTP port %s", public_id, candidate_port)
    return False


def _send_support_discord(*, public_id: str, plan: str, payload, severity: str = "info") -> bool:
    """Send privacy-minimized operational context when a Discord webhook is configured."""
    rank = {"info": 0, "warning": 1, "critical": 2}
    severity = str(severity or "info").strip().lower()
    minimum = str(support_channel_configuration()["discord_min_severity"])
    if rank.get(severity, 0) < rank[minimum]:
        logger.info("Discord alert suppressed for %s severity=%s minimum=%s", public_id, severity, minimum)
        return False
    webhook = os.getenv("SUPPORT_DISCORD_WEBHOOK_URL", "").strip()
    if not webhook:
        return False
    webhook_host = _discord_webhook_host(webhook)
    if not webhook_host:
        logger.error("Discord support webhook rejected: unsupported host or path")
        return False
    safe = lambda value: re.sub(r"[\r\n`@]+", " ", str(value or "")).strip()[:160]
    fields = [
        f"Ticket: {safe(public_id)}",
        f"Severidad: {safe(severity)}",
        f"Tipo: {safe(payload.category)}",
        f"Plan: {safe(plan) or 'desconocido'}",
        f"Versión: {safe(payload.app_version) or 'no indicada'}",
        f"Plataforma: {safe(getattr(payload, 'platform', None)) or 'no indicada'}",
        f"Pantalla: {safe(getattr(payload, 'screen', None)) or 'no indicada'}",
        f"Referencia: {safe(getattr(payload, 'error_reference', None)) or 'ninguna'}",
    ]
    # Automatic incidents: which request failed (method + path template, ids already
    # replaced) and its HTTP status. A screen fires several requests; without this the
    # alert cannot say which one broke. Never a query string, body or identity.
    operation = getattr(payload, "operation", None)
    if operation:
        fields.append(f"Operación: {safe(operation)}")
        fields.append(f"HTTP: {safe(getattr(payload, 'http_status', None)) or 'sin respuesta'}")
    role_id = os.getenv("SUPPORT_DISCORD_ALERT_ROLE_ID", "").strip()
    role_id = role_id if re.fullmatch(r"\d{5,30}", role_id) and severity == "critical" else ""
    mention = f"<@&{role_id}> " if role_id else ""
    allowed_mentions = {"parse": [], "roles": [role_id]} if role_id else {"parse": []}
    try:
        response = requests.post(
            webhook,
            json={
                "content": mention + f"**DINCR · {safe(severity).upper()}**\n```\n" + "\n".join(fields) + "\n```",
                "allowed_mentions": allowed_mentions,
            },
            timeout=10,
        )
        if response.status_code in {200, 204}:
            logger.info("Support Discord notification delivered for %s", public_id)
            return True
        logger.error(
            "Support Discord notification failed for %s host=%s status=%s",
            public_id, webhook_host, response.status_code,
        )
    except Exception:
        logger.exception("Support Discord notification failed for %s", public_id)
    return False


def _mark_discord_alerted(ticket_id: int) -> None:
    """Persist successful delivery so a failure burst cannot spam the alert channel."""
    try:
        with get_connection() as conn:
            conn.execute(
                "UPDATE feedback_reports SET discord_alerted_at=NOW(),updated_at=NOW() WHERE id=%s",
                (ticket_id,),
            )
            conn.commit()
    except Exception:
        logger.exception("Could not persist Discord alert delivery for ticket_id=%s", ticket_id)


def send_discord_test():
    """Owner-only route helper to validate the operational channel without user data."""
    if not support_channel_configuration()["discord_configured"]:
        raise HTTPException(503, "Discord no está configurado en Render.")
    public_id = f"DINCR-TEST-{secrets.token_hex(3).upper()}"
    payload = SimpleNamespace(
        category="health", app_version="server", platform="backend",
        screen="operaciones", error_reference=public_id,
    )
    if not _send_support_discord(public_id=public_id, plan="operaciones", payload=payload, severity="critical"):
        raise HTTPException(503, "Discord rechazó la alerta de prueba. Revisá el webhook en Render.")
    return {"status": "sent", "reference": public_id}


def _incident_severity(path: str, method: str, status: int) -> str:
    sensitive_operation = method.upper() != "GET" and any(
        marker in path for marker in (
            "/auth/me", "/billing/", "/receipt", "/user-product/finance/",
            "/transactions", "/debts", "/goals",
        )
    )
    if sensitive_operation or status >= 500:
        return "critical"
    return "warning"


def _sanitize_incident_path(value: str) -> str:
    path = str(value or "/unknown").split("?", 1)[0].split("#", 1)[0]
    path = re.sub(r"[0-9a-f]{8}-[0-9a-f-]{27,}", ":id", path, flags=re.I)
    path = re.sub(r"/\d+(?=/|$)", "/:id", path)
    return path[:160] or "/unknown"


def _sanitize_diagnostic_label(value: str | None) -> str | None:
    if not value:
        return None
    label = re.sub(r"[\r\n\t@`]+", " ", str(value)).strip()
    label = re.sub(r"\b\d{6,}\b", "[id]", label)
    return label[:80] or None


def _incident_fingerprint(payload) -> str:
    safe_screen = _sanitize_diagnostic_label(getattr(payload, "screen", None))
    status_family = "network" if not payload.status else "server" if payload.status >= 500 else "client"
    source = "|".join([
        safe_screen or _sanitize_incident_path(payload.path),
        status_family,
        str(getattr(payload, "platform", None) or "unknown")[:30],
        str(payload.app_version or "unknown")[:30],
    ])
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def launch_promotion_status(now: datetime | None = None):
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    active = current < LAUNCH_PROMOTION_END
    return {
        "code": LAUNCH_PROMOTION_CODE,
        "active": active,
        "ends_at": LAUNCH_PROMOTION_END.isoformat().replace("+00:00", "Z"),
        "message": (
            "Basic y VIP están gratis hasta el 31 de diciembre de 2026. No se realizará ningún cobro automático."
            if active else
            "La promoción terminó. Las compras de Basic y VIP desde Google Play y App Store estarán disponibles más adelante."
        ),
    }


def activate_launch_promotion(plan_code: str):
    if plan_code not in PRICES:
        raise HTTPException(400, "Plan promocional no válido.")
    if not launch_promotion_status()["active"]:
        raise HTTPException(409, "La promoción gratuita ya terminó.")
    account_id = get_current_account_id()
    with get_connection() as conn:
        ensure_schema(conn)
        plan = conn.execute("SELECT id FROM plans WHERE code=%s AND is_active=TRUE", (plan_code,)).fetchone()
        if not plan:
            raise HTTPException(404, "Plan no disponible.")
        conn.execute(
            """INSERT INTO account_subscriptions(
                   account_id,plan_id,status,access_source,started_at,expires_at,courtesy_note,
                   granted_by,granted_at,created_at,updated_at
               ) VALUES(%s,%s,'active','courtesy',NOW(),%s,%s,NULL,NOW(),NOW(),NOW())
               ON CONFLICT(account_id) DO UPDATE SET
                   plan_id=EXCLUDED.plan_id,status='active',access_source='courtesy',started_at=NOW(),
                   expires_at=EXCLUDED.expires_at,courtesy_note=EXCLUDED.courtesy_note,
                   granted_by=NULL,granted_at=NOW(),updated_at=NOW()""",
            (account_id, plan["id"], LAUNCH_PROMOTION_END, LAUNCH_PROMOTION_CODE),
        )
        conn.execute(
            "UPDATE accounts SET plan_selected=TRUE,onboarding_completed=TRUE,onboarding_level=%s,updated_at=NOW() WHERE id=%s",
            (plan_code, account_id),
        )
        conn.commit()
    record_event("launch_promotion_activated", "plan_selection")
    return {
        "status": "promotion_active",
        "promotion": launch_promotion_status(),
        "message": f"{plan_code.upper()} quedó activo gratis hasta el 31 de diciembre de 2026.",
    }


def ensure_schema(conn):
    """Fail fast when Product Ops migrations are missing, without runtime DDL.

    Schema creation and hardening belong to versioned migrations. Executing
    CREATE/ALTER/REVOKE here used relation-level locks on every request and
    allowed concurrent health/event requests to deadlock in PostgreSQL.
    """
    required_tables = (
        "product_events",
        "feedback_reports",
    )
    checks = ", ".join(
        f"to_regclass('public.{table_name}') IS NOT NULL AS {table_name}"
        for table_name in required_tables
    )
    state = conn.execute(f"SELECT {checks}").fetchone() or {}
    missing = [table_name for table_name in required_tables if not state.get(table_name)]
    if missing:
        raise RuntimeError(
            "Product Ops schema is incomplete; apply database migrations. "
            f"Missing tables: {', '.join(missing)}"
        )


def catalog():
    """Plans, prices and the launch promotion. Read-only: purchases happen in the stores."""
    promotion = launch_promotion_status()
    plans = [{"code": code, "regular_price_crc": info["regular"]} for code, info in PRICES.items()]
    return {"plans": plans, "promotion": promotion,
            "notice": promotion["message"] if promotion["active"] else "Las compras de Basic y VIP en Google Play y App Store estarán disponibles más adelante."}


def has_store_entitlement(conn, account_id: str, plan_code: str | None = None) -> bool:
    """A paid plan is active only through a verified App Store / Google Play subscription."""
    if not tables_exist(conn, ["store_subscriptions"]):
        return False
    return bool(conn.execute(
        """SELECT 1 FROM store_subscriptions
           WHERE account_id=%s AND status = ANY(%s::text[]) AND (%s::text IS NULL OR plan_code=%s)
             AND COALESCE(CASE WHEN status='trialing' THEN trial_ends_at END, current_period_end, 'infinity'::timestamptz) > NOW()""",
        (account_id, list(STORE_ENTITLED_STATES), plan_code, plan_code),
    ).fetchone())


def create_checkout(plan_code: str, accepted: bool, consent_version: str):
    if plan_code not in PRICES:
        raise HTTPException(400, "Plan de pago no válido.")
    if launch_promotion_status()["active"]:
        return activate_launch_promotion(plan_code)
    # Store billing and server-side purchase verification are not implemented yet.
    # Never issue an off-store payment order for access to mobile features.
    raise HTTPException(503, "Las compras de Basic y VIP en Google Play y App Store estarán disponibles más adelante. Podés seguir con el plan Gratis.")


def record_event(event_name, surface, success=True, duration_bucket=None, app_version=None):
    user = get_current_user()
    with get_connection() as conn:
        ensure_schema(conn)
        plan = conn.execute("""SELECT p.code FROM account_subscriptions s JOIN plans p ON p.id=s.plan_id WHERE s.account_id=%s""", (user["account_id"],)).fetchone()
        conn.execute("""INSERT INTO product_events(account_id,workspace_id,event_name,plan_code,surface,success,duration_bucket,app_version)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""", (user["account_id"], user.get("workspace_id"), event_name,
          (plan or {}).get("code"), surface, success, duration_bucket, app_version))
        conn.commit()
    return {"status": "recorded"}


def _record_event_safely(*args, **kwargs) -> None:
    try:
        record_event(*args, **kwargs)
    except Exception:
        logger.exception("Product telemetry failed after the primary operation completed")


def create_feedback(payload):
    user = get_current_user()
    with get_connection() as conn:
        ensure_schema(conn)
        identity = conn.execute(
            """SELECT a.primary_email,p.code AS plan_code FROM accounts a
               LEFT JOIN account_subscriptions s ON s.account_id=a.id
               LEFT JOIN plans p ON p.id=s.plan_id WHERE a.id=%s""",
            (user["account_id"],),
        ).fetchone() or {}
        row = conn.execute("""INSERT INTO feedback_reports(
            account_id,workspace_id,category,subject,message,plan_code,app_version,screen,error_reference
          ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
          RETURNING id,category,subject,status,created_at""", (user["account_id"], user.get("workspace_id"),
          payload.category, payload.subject.strip(), payload.message.strip(), identity.get("plan_code"), payload.app_version,
          payload.screen, payload.error_reference)).fetchone()
        conn.commit()
    _record_event_safely("feedback_submitted", "feedback")
    public_id = f"DINCR-{int(row['id']):06d}"
    email_sent = _send_support_email(
        public_id=public_id,
        email=identity.get("primary_email") or "no disponible",
        plan=identity.get("plan_code") or "",
        payload=payload,
    )
    discord_sent = _send_support_discord(
        public_id=public_id, plan=identity.get("plan_code") or "", payload=payload,
    )
    return {**row, "public_id": public_id, "email_sent": email_sent, "discord_sent": discord_sent}


# Client-reported incidents are untrusted input: one account may alert support at
# most this many times per hour (the incident itself is always recorded).
AUTOMATIC_ALERTS_PER_ACCOUNT_HOUR = 5


def create_automatic_incident(payload):
    user = get_current_user()
    safe_path = _sanitize_incident_path(payload.path)
    safe_screen = _sanitize_diagnostic_label(payload.screen)
    fingerprint = _incident_fingerprint(payload)
    severity = _incident_severity(safe_path, payload.method, payload.status)
    operation = f"{payload.method.upper()} {safe_path}"[:180]
    with get_connection() as conn:
        ensure_schema(conn)
        identity = conn.execute(
            """SELECT a.primary_email,p.code AS plan_code FROM accounts a
               LEFT JOIN account_subscriptions s ON s.account_id=a.id
               LEFT JOIN plans p ON p.id=s.plan_id WHERE a.id=%s""",
            (user["account_id"],),
        ).fetchone() or {}
        # Serialize the same account/fingerprint pair so simultaneous failures
        # cannot create duplicate tickets before either transaction commits.
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"{user['account_id']}:{fingerprint}",),
        )
        # Serialize the budget per account and count only incidents that actually
        # alerted, so a burst cannot race past it and noise cannot mute a real outage.
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"incident-alerts:{user['account_id']}",))
        recent_reports = conn.execute(
            """SELECT COUNT(*) AS total FROM feedback_reports
               WHERE account_id=%s AND source='automatic' AND discord_alerted_at >= NOW()-INTERVAL '1 hour'""",
            (user["account_id"],),
        ).fetchone() or {}
        alerts_allowed = int(recent_reports.get("total") or 0) < AUTOMATIC_ALERTS_PER_ACCOUNT_HOUR
        existing = conn.execute(
            """SELECT id,status,severity,occurrence_count,discord_alerted_at FROM feedback_reports
               WHERE account_id=%s AND fingerprint=%s AND source='automatic'
                 AND status IN ('new','reviewing') AND last_seen_at >= NOW()-INTERVAL '5 minutes'
               ORDER BY last_seen_at DESC LIMIT 1 FOR UPDATE""",
            (user["account_id"], fingerprint),
        ).fetchone()
        if existing:
            row = conn.execute(
                """UPDATE feedback_reports SET occurrence_count=occurrence_count+1,last_seen_at=NOW(),
                     updated_at=NOW(),request_id=%s,error_reference=%s,retry_count=GREATEST(retry_count,%s),
                     severity=CASE WHEN %s='critical' THEN 'critical' ELSE severity END,
                     affected_operations=CASE WHEN %s=ANY(affected_operations) THEN affected_operations
                       ELSE array_append(affected_operations,%s) END
                   WHERE id=%s RETURNING id,category,subject,status,severity,created_at,occurrence_count,
                     affected_operations,discord_alerted_at""",
                (payload.request_id, payload.error_reference, payload.retry_count, severity,
                 operation, operation, existing["id"]),
            ).fetchone()
            conn.commit()
            public_id = f"DINCR-{int(row['id']):06d}"
            discord_sent = False
            if alerts_allowed and row.get("severity") == "critical" and not row.get("discord_alerted_at"):
                escalation_payload = SimpleNamespace(
                    category="error", subject=row.get("subject") or "Incidente crítico",
                    message="Incidente correlacionado escalado a crítico.", app_version=payload.app_version,
                    screen=safe_screen or safe_path, error_reference=payload.error_reference or payload.request_id,
                    platform=payload.platform, operation=operation, http_status=payload.status or None,
                )
                discord_sent = _send_support_discord(
                    public_id=public_id, plan=identity.get("plan_code") or "",
                    payload=escalation_payload, severity="critical",
                )
                if discord_sent:
                    _mark_discord_alerted(row["id"])
            return {**row, "public_id": public_id, "deduplicated": True,
                    "email_sent": False, "discord_sent": discord_sent}

        subject = f"Fallo automático · {safe_screen or safe_path}"[:140]
        message = "\n".join([
            "DINCR detectó este incidente automáticamente.",
            f"Operación: {payload.method.upper()} {safe_path}",
            f"Estado HTTP: {payload.status or 'sin respuesta'}",
            f"Tipo: {payload.error_type}",
            f"Reintentos seguros: {payload.retry_count}",
            f"Request ID: {payload.request_id}",
            "No se adjuntaron payloads, secretos ni información financiera.",
        ])
        row = conn.execute(
            """INSERT INTO feedback_reports(
                 account_id,workspace_id,category,subject,message,plan_code,app_version,source,severity,
                 fingerprint,request_id,error_reference,screen,platform,retry_count,affected_operations
               ) VALUES(%s,%s,'error',%s,%s,%s,%s,'automatic',%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id,category,subject,status,severity,created_at,occurrence_count,
                 affected_operations,discord_alerted_at""",
            (user["account_id"], user.get("workspace_id"), subject, message, identity.get("plan_code"),
             payload.app_version, severity, fingerprint, payload.request_id, payload.error_reference,
             safe_screen, payload.platform, payload.retry_count, [operation]),
        ).fetchone()
        conn.commit()

    public_id = f"DINCR-{int(row['id']):06d}"
    notification_payload = SimpleNamespace(
        category="error", subject=subject, message=message, app_version=payload.app_version,
        screen=safe_screen or safe_path, error_reference=payload.error_reference or payload.request_id,
        platform=payload.platform, operation=operation, http_status=payload.status or None,
    )
    email_sent = alerts_allowed and _send_support_email(
        public_id=public_id, email=identity.get("primary_email") or "no disponible",
        plan=identity.get("plan_code") or "", payload=notification_payload,
    )
    discord_sent = alerts_allowed and _send_support_discord(
        public_id=public_id, plan=identity.get("plan_code") or "",
        payload=notification_payload, severity=severity,
    )
    if discord_sent:
        _mark_discord_alerted(row["id"])
    _record_event_safely("api_error", safe_screen or safe_path, success=False, app_version=payload.app_version)
    return {**row, "public_id": public_id, "deduplicated": False,
            "email_sent": email_sent, "discord_sent": discord_sent, "severity": severity}


def list_feedback():
    account_id = get_current_account_id()
    with get_connection() as conn:
        ensure_schema(conn)
        rows = conn.execute("""SELECT id,category,subject,message,status,owner_notes,source,severity,
          occurrence_count,last_seen_at,affected_operations,discord_alerted_at,user_resolution,user_resolution_at,created_at,updated_at
          FROM feedback_reports WHERE account_id=%s ORDER BY created_at DESC LIMIT 30""", (account_id,)).fetchall()
        conn.commit()
    return [{**r, "public_id": f"DINCR-{int(r['id']):06d}"} for r in rows]


def platform_health():
    """Return privacy-safe operational health derived from recent automatic incidents."""
    with get_connection() as conn:
        ensure_schema(conn)
        row = conn.execute(
            """SELECT COUNT(*) AS active_incidents,
                      COALESCE(SUM(occurrence_count),0) AS occurrences,
                      COUNT(DISTINCT account_id) AS affected_accounts,
                      COUNT(DISTINCT account_id) FILTER (WHERE severity='critical') AS critical_accounts,
                      MAX(last_seen_at) AS last_incident_at
               FROM feedback_reports
               WHERE source='automatic' AND status IN ('new','reviewing')
                 AND COALESCE(user_resolution,'still_happening') <> 'resolved'
                 AND last_seen_at >= NOW()-INTERVAL '15 minutes'"""
        ).fetchone() or {}
        conn.commit()
    affected = int(row.get("affected_accounts") or 0)
    critical = int(row.get("critical_accounts") or 0)
    status = "major_outage" if critical >= 3 else "degraded" if affected >= 2 else "operational"
    return {
        "status": status,
        "active_incidents": int(row.get("active_incidents") or 0),
        "occurrences": int(row.get("occurrences") or 0),
        "affected_accounts": affected,
        "last_incident_at": row.get("last_incident_at"),
        "checked_at": datetime.now(timezone.utc),
    }


def update_user_feedback_resolution(ticket_id: int, resolution: str):
    user = get_current_user()
    account_id = user["account_id"]
    with get_connection() as conn:
        ensure_schema(conn)
        ticket = conn.execute(
            """SELECT f.id,f.category,f.subject,f.message,f.plan_code,f.app_version,
                      f.screen,f.error_reference,COALESCE(a.primary_email,'no disponible') AS email
               FROM feedback_reports f JOIN accounts a ON a.id=f.account_id
               WHERE f.id=%s AND f.account_id=%s FOR UPDATE""",
            (ticket_id, account_id),
        ).fetchone()
        if not ticket:
            raise HTTPException(404, "Reporte no encontrado.")
        status = "resolved" if resolution == "resolved" else "reviewing"
        row = conn.execute(
            """UPDATE feedback_reports SET status=%s,user_resolution=%s,user_resolution_at=NOW(),
                     resolved_at=CASE WHEN %s='resolved' THEN NOW() ELSE NULL END,updated_at=NOW()
               WHERE id=%s AND account_id=%s
               RETURNING id,category,subject,status,user_resolution,user_resolution_at,updated_at""",
            (status, resolution, resolution, ticket_id, account_id),
        ).fetchone()
        conn.commit()

    public_id = f"DINCR-{int(row['id']):06d}"
    label = "El usuario confirmó que se resolvió." if resolution == "resolved" else "El usuario confirmó que el problema continúa."
    notification = SimpleNamespace(
        category="status",
        subject=f"Actualización · {ticket['subject']}",
        message=label,
        app_version=ticket.get("app_version"),
        screen=ticket.get("screen"),
        error_reference=ticket.get("error_reference"),
        platform=None,
    )
    email_sent = _send_support_email(
        public_id=public_id,
        email=ticket.get("email") or "no disponible",
        plan=ticket.get("plan_code") or "",
        payload=notification,
    )
    discord_sent = _send_support_discord(
        public_id=public_id,
        plan=ticket.get("plan_code") or "",
        payload=notification,
        severity="warning" if resolution == "still_happening" else "info",
    )
    return {**row, "public_id": public_id, "email_sent": email_sent, "discord_sent": discord_sent}


def resend_feedback_email(ticket_id: int):
    """Let an owner retry delivery of an already-saved support ticket."""
    with get_connection() as conn:
        ensure_schema(conn)
        row = conn.execute(
            """SELECT f.id,f.category,f.subject,f.message,f.plan_code,f.app_version,
                      COALESCE(a.primary_email,'no disponible') AS email
               FROM feedback_reports f
               LEFT JOIN accounts a ON a.id=f.account_id
               WHERE f.id=%s""",
            (ticket_id,),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Reporte no encontrado.")
    public_id = f"DINCR-{int(row['id']):06d}"
    payload = SimpleNamespace(
        category=row["category"], subject=row["subject"], message=row["message"],
        app_version=row.get("app_version"), screen=None, error_reference=None,
    )
    sent = _send_support_email(
        public_id=public_id,
        email=row.get("email") or "no disponible",
        plan=row.get("plan_code") or "",
        payload=payload,
    )
    if not sent:
        raise HTTPException(
            503,
            "El reporte está guardado, pero Gmail rechazó el envío. Revisá la contraseña de aplicación en Render.",
        )
    return {"status": "sent", "public_id": public_id, "email_sent": True}


def owner_dashboard():
    with get_connection() as conn:
        ensure_schema(conn)
        promotion_rows = conn.execute(
            """SELECT p.code AS plan_code,COUNT(*) AS used
               FROM account_subscriptions s JOIN plans p ON p.id=s.plan_id
               WHERE s.status='active' AND s.access_source='courtesy' AND s.courtesy_note=%s
                 AND s.expires_at>NOW() GROUP BY p.code""",
            (LAUNCH_PROMOTION_CODE,),
        ).fetchall()
        promotional = {row["plan_code"]: int(row["used"]) for row in promotion_rows}
        events = conn.execute("""SELECT event_name,COUNT(*) AS uses,COUNT(DISTINCT account_id) AS users
          FROM product_events WHERE created_at>=NOW()-INTERVAL '30 days' GROUP BY event_name ORDER BY uses DESC LIMIT 20""").fetchall()
        tickets = conn.execute("""SELECT f.id,f.category,f.subject,f.message,f.status,f.owner_notes,
          f.source,f.severity,f.occurrence_count,f.last_seen_at,f.affected_operations,f.discord_alerted_at,f.user_resolution,f.user_resolution_at,
          f.created_at,a.primary_email AS email
          FROM feedback_reports f JOIN accounts a ON a.id=f.account_id ORDER BY CASE f.status WHEN 'new' THEN 1 WHEN 'reviewing' THEN 2 ELSE 3 END,f.created_at DESC LIMIT 100""").fetchall()
        release_policies = conn.execute(
            """SELECT platform,minimum_supported_version,latest_version,update_url,
                      message_es,message_en,is_active,updated_at
               FROM app_release_policies ORDER BY platform"""
        ).fetchall()
        feature_flags = conn.execute(
            """SELECT flag_key,display_name,description,enabled,safe_default_enabled,
                      disabled_message_es,disabled_message_en,updated_at
               FROM app_feature_flags ORDER BY display_name"""
        ).fetchall()
        feature_flag_audit = conn.execute(
            """SELECT flag_key,previous_enabled,new_enabled,reason,changed_at
               FROM app_feature_flag_audit ORDER BY changed_at DESC LIMIT 20"""
        ).fetchall()
        email_monitor = build_email_monitor_dashboard(conn)
        conn.commit()
    return {"promotion": {**launch_promotion_status(), "plans": promotional},
            "support_email": support_email_configuration(),
            "support_channels": support_channel_configuration(),
            "feature_usage_30d": events,
            "tickets": [{**r, "public_id": f"DINCR-{int(r['id']):06d}"} for r in tickets],
            "release_policies": release_policies,
            "feature_flags": feature_flags,
            "feature_flag_audit": feature_flag_audit,
            "email_monitor": email_monitor}


def update_feedback(ticket_id: int, payload):
    with get_connection() as conn:
        ensure_schema(conn)
        row = conn.execute("""UPDATE feedback_reports SET status=%s,owner_notes=%s,updated_at=NOW(),
          resolved_at=CASE WHEN %s IN ('resolved','dismissed') THEN NOW() ELSE NULL END WHERE id=%s
          RETURNING id,status,owner_notes,updated_at""", (payload.status, payload.owner_notes, payload.status, ticket_id)).fetchone()
        if not row: raise HTTPException(404, "Reporte no encontrado.")
        conn.commit()
    return {**row, "public_id": f"DINCR-{int(row['id']):06d}"}
