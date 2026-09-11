import hashlib
import os
import re
import secrets
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException

from backend.auth.current_user import get_current_account_id, get_current_user, get_current_workspace_id
from backend.core.database import get_connection

BETA_CODE = "beta-2026-01"
PRICES = {
    "basic": {"beta": 1990, "regular": 2990, "slots": 15},
    "vip": {"beta": 3990, "regular": 5990, "slots": 15},
}
PAYMENT_CODE_PATTERN = re.compile(r"\bFINVA-[A-Z0-9]{6}\b", re.I)
RECEIPT_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
MAX_RECEIPT_BYTES = 5 * 1024 * 1024


def _sinpe_instructions():
    return {
        "method": "SINPE Móvil",
        "recipient": os.getenv("FINVA_SINPE_RECIPIENT", "").strip(),
        "phone": os.getenv("FINVA_SINPE_PHONE", "").strip(),
        "message": "Copiá el código y pegalo en el detalle del SINPE. Luego subí el comprobante.",
    }


def _public_order(order):
    if not order:
        return None
    allowed = {
        "id", "plan_code", "amount", "currency", "status", "provider", "payment_code",
        "code_expires_at", "receipt_submitted_at", "receipt_status", "verified_at",
        "verification_source", "created_at", "updated_at",
    }
    return {key: value for key, value in dict(order).items() if key in allowed}


def _new_payment_code(conn):
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    for _ in range(20):
        code = "FINVA-" + "".join(secrets.choice(alphabet) for _ in range(6))
        if not conn.execute("SELECT 1 FROM billing_orders WHERE payment_code=%s", (code,)).fetchone():
            return code
    raise HTTPException(503, "No se pudo generar un código de pago. Intentá nuevamente.")


def _as_utc(value):
    if not value:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _valid_receipt_signature(content_type: str, content: bytes):
    signatures = {
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
        "image/png": content.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/webp": content.startswith(b"RIFF") and content[8:12] == b"WEBP",
        "application/pdf": content.startswith(b"%PDF-"),
    }
    return signatures.get(content_type, False)


def ensure_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS finva_beta_programs (
      code TEXT PRIMARY KEY, active BOOLEAN NOT NULL DEFAULT TRUE,
      beta_duration_months INTEGER NOT NULL DEFAULT 3,
      basic_slots INTEGER NOT NULL DEFAULT 15, vip_slots INTEGER NOT NULL DEFAULT 15,
      basic_beta_price_crc NUMERIC(12,2) NOT NULL DEFAULT 1990,
      vip_beta_price_crc NUMERIC(12,2) NOT NULL DEFAULT 3990,
      basic_regular_price_crc NUMERIC(12,2) NOT NULL DEFAULT 2990,
      vip_regular_price_crc NUMERIC(12,2) NOT NULL DEFAULT 5990,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    # This table is keyed by ``code`` and intentionally has no numeric ``id``.
    # Be explicit so the legacy database adapter does not append ``RETURNING id``.
    conn.execute(
        """INSERT INTO finva_beta_programs(code) VALUES(%s)
           ON CONFLICT(code) DO NOTHING RETURNING code""",
        (BETA_CODE,),
    )
    conn.execute("""CREATE TABLE IF NOT EXISTS billing_orders (
      id BIGSERIAL PRIMARY KEY, account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
      workspace_id UUID, plan_code TEXT NOT NULL CHECK(plan_code IN ('basic','vip')),
      amount NUMERIC(12,2) NOT NULL, currency TEXT NOT NULL DEFAULT 'CRC',
      status TEXT NOT NULL DEFAULT 'payment_pending' CHECK(status IN ('payment_pending','paid','failed','canceled','expired','refunded')),
      provider TEXT NOT NULL DEFAULT 'sinpe_mobile', provider_order_id TEXT, beta_code TEXT,
      beta_price BOOLEAN NOT NULL DEFAULT TRUE, consent_version TEXT NOT NULL,
      consent_at TIMESTAMPTZ NOT NULL, paid_at TIMESTAMPTZ, payment_code TEXT,
      code_expires_at TIMESTAMPTZ, receipt_filename TEXT, receipt_content_type TEXT,
      receipt_size INTEGER, receipt_sha256 TEXT, receipt_data BYTEA,
      receipt_submitted_at TIMESTAMPTZ, receipt_status TEXT NOT NULL DEFAULT 'not_submitted',
      verified_at TIMESTAMPTZ, verification_source TEXT, bank_reference TEXT, payer_name TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_billing_orders_status ON billing_orders(status,created_at DESC)""")
    for ddl in [
        "ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS payment_code TEXT",
        "ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS code_expires_at TIMESTAMPTZ",
        "ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS receipt_filename TEXT",
        "ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS receipt_content_type TEXT",
        "ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS receipt_size INTEGER",
        "ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS receipt_sha256 TEXT",
        "ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS receipt_data BYTEA",
        "ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS receipt_submitted_at TIMESTAMPTZ",
        "ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS receipt_status TEXT NOT NULL DEFAULT 'not_submitted'",
        "ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ",
        "ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS verification_source TEXT",
        "ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS bank_reference TEXT",
        "ALTER TABLE billing_orders ADD COLUMN IF NOT EXISTS payer_name TEXT",
    ]:
        conn.execute(ddl)
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_billing_orders_payment_code
      ON billing_orders(payment_code) WHERE payment_code IS NOT NULL""")
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_billing_orders_receipt_sha256
      ON billing_orders(receipt_sha256) WHERE receipt_sha256 IS NOT NULL""")
    conn.execute("""CREATE TABLE IF NOT EXISTS billing_subscriptions (
      account_id UUID PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE, workspace_id UUID,
      plan_code TEXT NOT NULL CHECK(plan_code IN ('basic','vip')),
      status TEXT NOT NULL CHECK(status IN ('payment_pending','active','past_due','canceled','expired','refunded')),
      provider TEXT NOT NULL DEFAULT 'sandbox', provider_subscription_id TEXT, beta_code TEXT,
      beta_ends_at TIMESTAMPTZ, current_period_start TIMESTAMPTZ, current_period_end TIMESTAMPTZ,
      cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE, paid_price_crc NUMERIC(12,2),
      regular_price_crc NUMERIC(12,2), created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    conn.execute("""CREATE TABLE IF NOT EXISTS product_events (
      id BIGSERIAL PRIMARY KEY, account_id UUID REFERENCES accounts(id) ON DELETE SET NULL,
      workspace_id UUID, event_name TEXT NOT NULL, plan_code TEXT, surface TEXT NOT NULL,
      success BOOLEAN NOT NULL DEFAULT TRUE, duration_bucket TEXT, app_version TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_product_events_created ON product_events(created_at DESC)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS feedback_reports (
      id BIGSERIAL PRIMARY KEY, account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
      workspace_id UUID, category TEXT NOT NULL, subject TEXT NOT NULL, message TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'new', plan_code TEXT, app_version TEXT, owner_notes TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), resolved_at TIMESTAMPTZ)""")


def _counts(conn):
    rows = conn.execute("""SELECT plan_code,COUNT(*) AS used FROM billing_subscriptions
      WHERE status='active' AND beta_code=%s GROUP BY plan_code""", (BETA_CODE,)).fetchall()
    return {r["plan_code"]: int(r["used"]) for r in rows}


def catalog():
    account_id = get_current_account_id()
    with get_connection() as conn:
        ensure_schema(conn)
        used = _counts(conn)
        order = conn.execute("""SELECT id,plan_code,amount,currency,status,provider,payment_code,code_expires_at,
          receipt_submitted_at,receipt_status,verified_at,verification_source,created_at,updated_at FROM billing_orders
          WHERE account_id=%s ORDER BY created_at DESC LIMIT 1""", (account_id,)).fetchone()
        if order and order["status"] == "payment_pending" and not order.get("payment_code"):
            order = conn.execute("""UPDATE billing_orders SET provider='sinpe_mobile',payment_code=%s,
              code_expires_at=NOW()+INTERVAL '2 hours',updated_at=NOW() WHERE id=%s
              RETURNING id,plan_code,amount,currency,status,provider,payment_code,code_expires_at,
                receipt_submitted_at,receipt_status,verified_at,verification_source,created_at,updated_at""",
              (_new_payment_code(conn), order["id"])).fetchone()
        subscription = conn.execute("SELECT * FROM billing_subscriptions WHERE account_id=%s", (account_id,)).fetchone()
        conn.commit()
    plans = []
    for code, info in PRICES.items():
        plans.append({"code": code, "beta_price_crc": info["beta"], "regular_price_crc": info["regular"],
                      "beta_months": 3, "slots_total": info["slots"], "slots_remaining": max(0, info["slots"] - used.get(code, 0))})
    return {"program": BETA_CODE, "plans": plans, "order": _public_order(order), "subscription": subscription,
            "payment": _sinpe_instructions(),
            "notice": "Durante la beta pagás por SINPE Móvil. El plan se activa cuando FINVA confirma el depósito."}


def create_checkout(plan_code: str, accepted: bool, consent_version: str):
    if plan_code not in PRICES:
        raise HTTPException(400, "Plan de pago no válido.")
    if not accepted:
        raise HTTPException(422, "Debés aceptar las condiciones del precio beta.")
    account_id, workspace_id = get_current_account_id(), get_current_workspace_id()
    with get_connection() as conn:
        ensure_schema(conn)
        conn.execute("""UPDATE billing_orders SET status='expired',updated_at=NOW()
          WHERE account_id=%s AND status='payment_pending' AND receipt_submitted_at IS NULL
            AND code_expires_at IS NOT NULL AND code_expires_at<NOW()""", (account_id,))
        used = _counts(conn).get(plan_code, 0)
        already_occupies_slot = conn.execute(
            "SELECT 1 FROM billing_subscriptions WHERE account_id=%s AND plan_code=%s AND status='active' AND beta_code=%s",
            (account_id, plan_code, BETA_CODE),
        ).fetchone()
        if not already_occupies_slot and used >= PRICES[plan_code]["slots"]:
            raise HTTPException(409, "Los cupos beta de este plan están completos.")
        existing = conn.execute("""SELECT id,plan_code,amount,currency,status,provider,payment_code,code_expires_at,
          receipt_submitted_at,receipt_status,created_at,updated_at FROM billing_orders
          WHERE account_id=%s AND plan_code=%s AND status='payment_pending' ORDER BY created_at DESC LIMIT 1""", (account_id, plan_code)).fetchone()
        if existing:
            if not existing.get("payment_code"):
                existing = conn.execute("""UPDATE billing_orders SET provider='sinpe_mobile',payment_code=%s,
                  code_expires_at=NOW()+INTERVAL '2 hours',updated_at=NOW() WHERE id=%s
                  RETURNING id,plan_code,amount,currency,status,provider,payment_code,code_expires_at,
                    receipt_submitted_at,receipt_status,created_at,updated_at""",
                  (_new_payment_code(conn), existing["id"])).fetchone()
            conn.commit()
            return {"status": "payment_pending", "order": _public_order(existing), "payment": _sinpe_instructions(),
                    "message": "Ya tenés una solicitud pendiente. Completá el SINPE y subí el comprobante."}
        conn.execute("""UPDATE billing_orders SET status='canceled',updated_at=NOW()
          WHERE account_id=%s AND status='payment_pending'""", (account_id,))
        payment_code = _new_payment_code(conn)
        order = conn.execute("""INSERT INTO billing_orders(
            account_id,workspace_id,plan_code,amount,provider,beta_code,consent_version,consent_at,payment_code,code_expires_at
          ) VALUES(%s,%s,%s,%s,'sinpe_mobile',%s,%s,NOW(),%s,NOW()+INTERVAL '2 hours')
          RETURNING id,plan_code,amount,currency,status,provider,payment_code,code_expires_at,
            receipt_submitted_at,receipt_status,created_at,updated_at""",
          (account_id, workspace_id, plan_code, PRICES[plan_code]["beta"], BETA_CODE, consent_version, payment_code)).fetchone()
        conn.commit()
    record_event("checkout_started", "plan_selection")
    return {"status": "payment_pending", "order": _public_order(order), "payment": _sinpe_instructions(),
            "message": "Código listo. Pegalo en el detalle del SINPE y subí el comprobante."}


def has_active_payment(conn, account_id: str, plan_code: str | None = None):
    ensure_schema(conn)
    params = [account_id]
    extra = ""
    if plan_code:
        extra = " AND plan_code=%s"
        params.append(plan_code)
    return bool(conn.execute(f"SELECT 1 FROM billing_subscriptions WHERE account_id=%s AND status='active'{extra}", tuple(params)).fetchone())


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


def create_feedback(payload):
    user = get_current_user()
    with get_connection() as conn:
        ensure_schema(conn)
        plan = conn.execute("""SELECT p.code FROM account_subscriptions s JOIN plans p ON p.id=s.plan_id WHERE s.account_id=%s""", (user["account_id"],)).fetchone()
        row = conn.execute("""INSERT INTO feedback_reports(account_id,workspace_id,category,subject,message,plan_code)
          VALUES(%s,%s,%s,%s,%s,%s) RETURNING id,category,subject,status,created_at""", (user["account_id"], user.get("workspace_id"),
          payload.category, payload.subject.strip(), payload.message.strip(), (plan or {}).get("code"))).fetchone()
        conn.commit()
    record_event("feedback_submitted", "feedback")
    return {**row, "public_id": f"FINVA-{int(row['id']):06d}"}


def list_feedback():
    account_id = get_current_account_id()
    with get_connection() as conn:
        ensure_schema(conn)
        rows = conn.execute("""SELECT id,category,subject,message,status,owner_notes,created_at,updated_at
          FROM feedback_reports WHERE account_id=%s ORDER BY created_at DESC LIMIT 30""", (account_id,)).fetchall()
        conn.commit()
    return [{**r, "public_id": f"FINVA-{int(r['id']):06d}"} for r in rows]


def owner_dashboard():
    with get_connection() as conn:
        ensure_schema(conn)
        used = _counts(conn)
        pending = conn.execute("""SELECT o.id,o.plan_code,o.amount,o.currency,o.payment_code,o.receipt_submitted_at,
          o.receipt_status,o.created_at,a.primary_email AS email,a.display_name
          FROM billing_orders o JOIN accounts a ON a.id=o.account_id WHERE o.status='payment_pending' ORDER BY o.created_at""").fetchall()
        events = conn.execute("""SELECT event_name,COUNT(*) AS uses,COUNT(DISTINCT account_id) AS users
          FROM product_events WHERE created_at>=NOW()-INTERVAL '30 days' GROUP BY event_name ORDER BY uses DESC LIMIT 20""").fetchall()
        tickets = conn.execute("""SELECT f.id,f.category,f.subject,f.message,f.status,f.owner_notes,f.created_at,a.primary_email AS email
          FROM feedback_reports f JOIN accounts a ON a.id=f.account_id ORDER BY CASE f.status WHEN 'new' THEN 1 WHEN 'reviewing' THEN 2 ELSE 3 END,f.created_at DESC LIMIT 100""").fetchall()
        conn.commit()
    return {"beta": {code: {"used": used.get(code, 0), "total": info["slots"], "remaining": info["slots"]-used.get(code, 0)} for code, info in PRICES.items()},
            "pending_orders": pending, "feature_usage_30d": events,
            "tickets": [{**r, "public_id": f"FINVA-{int(r['id']):06d}"} for r in tickets]}


def submit_receipt(order_id: int, filename: str, content_type: str, content: bytes):
    if content_type not in RECEIPT_CONTENT_TYPES:
        raise HTTPException(415, "Subí una imagen JPG, PNG, WEBP o un PDF.")
    if not content:
        raise HTTPException(422, "El comprobante está vacío.")
    if len(content) > MAX_RECEIPT_BYTES:
        raise HTTPException(413, "El comprobante no puede superar 5 MB.")
    if not _valid_receipt_signature(content_type, content):
        raise HTTPException(415, "El contenido del archivo no coincide con un comprobante permitido.")
    account_id = get_current_account_id()
    digest = hashlib.sha256(content).hexdigest()
    with get_connection() as conn:
        ensure_schema(conn)
        duplicate = conn.execute(
            "SELECT id FROM billing_orders WHERE receipt_sha256=%s AND id<>%s LIMIT 1",
            (digest, order_id),
        ).fetchone()
        if duplicate:
            raise HTTPException(409, "Este comprobante ya fue utilizado en otra solicitud.")
        order = conn.execute(
            "SELECT id,status,code_expires_at FROM billing_orders WHERE id=%s AND account_id=%s FOR UPDATE",
            (order_id, account_id),
        ).fetchone()
        if not order or order["status"] != "payment_pending":
            raise HTTPException(404, "Solicitud de pago pendiente no encontrada.")
        expires_at = _as_utc(order.get("code_expires_at"))
        if expires_at and expires_at < datetime.now(timezone.utc):
            conn.execute("UPDATE billing_orders SET status='expired',updated_at=NOW() WHERE id=%s", (order_id,))
            conn.commit()
            raise HTTPException(409, "El código venció. Creá una solicitud nueva antes de pagar.")
        row = conn.execute("""UPDATE billing_orders SET receipt_filename=%s,receipt_content_type=%s,
          receipt_size=%s,receipt_sha256=%s,receipt_data=%s,receipt_submitted_at=NOW(),
          receipt_status='submitted',updated_at=NOW() WHERE id=%s
          RETURNING id,plan_code,amount,currency,status,provider,payment_code,code_expires_at,
            receipt_submitted_at,receipt_status,created_at,updated_at""",
          ((filename or "comprobante")[:180], content_type, len(content), digest, content, order_id)).fetchone()
        conn.commit()
    return {"status": "receipt_submitted", "order": _public_order(row),
            "message": "Comprobante recibido. FINVA verificará el depósito con la confirmación bancaria."}


def get_receipt(order_id: int):
    with get_connection() as conn:
        ensure_schema(conn)
        row = conn.execute("""SELECT receipt_filename,receipt_content_type,receipt_data
          FROM billing_orders WHERE id=%s""", (order_id,)).fetchone()
        conn.commit()
    if not row or not row.get("receipt_data"):
        raise HTTPException(404, "Esta orden no tiene comprobante.")
    return row


def _activate_order(conn, order, verification_source: str, bank_reference: str | None = None, payer_name: str | None = None):
    already_occupies_slot = conn.execute(
        "SELECT 1 FROM billing_subscriptions WHERE account_id=%s AND plan_code=%s AND status='active' AND beta_code=%s",
        (order["account_id"], order["plan_code"], BETA_CODE),
    ).fetchone()
    if not already_occupies_slot and _counts(conn).get(order["plan_code"], 0) >= PRICES[order["plan_code"]]["slots"]:
        raise HTTPException(409, "No quedan cupos beta.")
    conn.execute("""UPDATE billing_orders SET status='paid',paid_at=NOW(),verified_at=NOW(),
      verification_source=%s,bank_reference=COALESCE(%s,bank_reference),payer_name=COALESCE(%s,payer_name),
      provider_order_id=COALESCE(%s,provider_order_id),receipt_status='verified',updated_at=NOW() WHERE id=%s""",
      (verification_source, bank_reference, payer_name, bank_reference, order["id"]))
    conn.execute("""INSERT INTO billing_subscriptions(account_id,workspace_id,plan_code,status,provider,beta_code,beta_ends_at,current_period_start,current_period_end,paid_price_crc,regular_price_crc)
      VALUES(%s,%s,%s,'active','sinpe_mobile',%s,NOW()+INTERVAL '3 months',NOW(),NOW()+INTERVAL '1 month',%s,%s)
      ON CONFLICT(account_id) DO UPDATE SET plan_code=EXCLUDED.plan_code,status='active',provider='sinpe_mobile',beta_code=EXCLUDED.beta_code,
      beta_ends_at=CASE WHEN billing_subscriptions.beta_code=EXCLUDED.beta_code THEN billing_subscriptions.beta_ends_at ELSE EXCLUDED.beta_ends_at END,
      current_period_start=NOW(),current_period_end=EXCLUDED.current_period_end,
      paid_price_crc=EXCLUDED.paid_price_crc,regular_price_crc=EXCLUDED.regular_price_crc,updated_at=NOW()
      RETURNING account_id""",
      (order["account_id"], order["workspace_id"], order["plan_code"], BETA_CODE, order["amount"], PRICES[order["plan_code"]]["regular"]))
    plan = conn.execute("SELECT id FROM plans WHERE code=%s", (order["plan_code"],)).fetchone()
    conn.execute("""INSERT INTO account_subscriptions(account_id,plan_id,status,access_source,started_at,last_payment_at,created_at,updated_at)
      VALUES(%s,%s,'active','self_service',NOW(),NOW(),NOW(),NOW()) ON CONFLICT(account_id) DO UPDATE SET
      plan_id=EXCLUDED.plan_id,status='active',access_source='self_service',started_at=NOW(),last_payment_at=NOW(),updated_at=NOW()""",
      (order["account_id"], plan["id"]))
    conn.execute("UPDATE accounts SET plan_selected=TRUE,onboarding_completed=FALSE,updated_at=NOW() WHERE id=%s", (order["account_id"],))


def match_sinpe_payment(conn, candidate: dict):
    """Activate a beta order only from a parsed incoming BAC SINPE confirmation.

    The bank email is the source of truth. The uploaded receipt is required as
    user-provided evidence but never activates a plan by itself.
    """
    if candidate.get("transaction_type") not in {"income", "reimbursement"}:
        return None
    if str(candidate.get("movement_direction") or "").lower() != "in":
        return None
    searchable = " ".join(str(candidate.get(key) or "") for key in ("description", "notes", "raw_description"))
    code_match = PAYMENT_CODE_PATTERN.search(searchable.upper())
    if not code_match:
        return None
    configured_phone = re.sub(r"\D", "", os.getenv("FINVA_SINPE_PHONE", ""))[-8:]
    destination_match = re.search(r"telefono destino:\s*(\d{8})", searchable, re.I)
    if configured_phone and (
        not destination_match or destination_match.group(1)[-8:] != configured_phone
    ):
        return None
    code = code_match.group(0).upper()
    order = conn.execute("""SELECT * FROM billing_orders WHERE payment_code=%s AND status='payment_pending'
      AND receipt_submitted_at IS NOT NULL FOR UPDATE""", (code,)).fetchone()
    try:
        amount_matches = Decimal(str(order["amount"])) == Decimal(str(candidate.get("amount") or 0))
    except (InvalidOperation, TypeError, ValueError):
        amount_matches = False
    if not order or not amount_matches:
        return None
    notes = str(candidate.get("notes") or "")
    reference = re.search(r"referencia\s+(\d{5,})", notes, re.I)
    payer = re.search(r"payer:\s*([^|]+)", notes, re.I)
    _activate_order(
        conn,
        order,
        "gmail_bac_sinpe",
        reference.group(1) if reference else None,
        payer.group(1).strip() if payer else None,
    )
    return {"order_id": order["id"], "plan_code": order["plan_code"], "payment_code": code}


def resolve_test_order(order_id: int, action: str):
    with get_connection() as conn:
        ensure_schema(conn)
        order = conn.execute("SELECT * FROM billing_orders WHERE id=%s FOR UPDATE", (order_id,)).fetchone()
        if not order or order["status"] != "payment_pending":
            raise HTTPException(404, "Orden pendiente no encontrada.")
        if action == "reject":
            conn.execute("UPDATE billing_orders SET status='failed',receipt_status='rejected',updated_at=NOW() WHERE id=%s", (order_id,))
            conn.commit(); return {"status": "failed"}
        _activate_order(conn, order, "owner_manual")
        conn.commit()
    return {"status": "active", "plan": order["plan_code"]}


def update_feedback(ticket_id: int, payload):
    with get_connection() as conn:
        ensure_schema(conn)
        row = conn.execute("""UPDATE feedback_reports SET status=%s,owner_notes=%s,updated_at=NOW(),
          resolved_at=CASE WHEN %s IN ('resolved','dismissed') THEN NOW() ELSE NULL END WHERE id=%s
          RETURNING id,status,owner_notes,updated_at""", (payload.status, payload.owner_notes, payload.status, ticket_id)).fetchone()
        if not row: raise HTTPException(404, "Reporte no encontrado.")
        conn.commit()
    return {**row, "public_id": f"FINVA-{int(row['id']):06d}"}
