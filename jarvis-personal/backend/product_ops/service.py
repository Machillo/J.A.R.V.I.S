from fastapi import HTTPException

from backend.auth.current_user import get_current_account_id, get_current_user, get_current_workspace_id
from backend.core.database import get_connection

BETA_CODE = "beta-2026-01"
PRICES = {
    "basic": {"beta": 1990, "regular": 2990, "slots": 15},
    "vip": {"beta": 3990, "regular": 5990, "slots": 15},
}


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
    conn.execute("""INSERT INTO finva_beta_programs(code) VALUES(%s) ON CONFLICT(code) DO NOTHING""", (BETA_CODE,))
    conn.execute("""CREATE TABLE IF NOT EXISTS billing_orders (
      id BIGSERIAL PRIMARY KEY, account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
      workspace_id UUID, plan_code TEXT NOT NULL CHECK(plan_code IN ('basic','vip')),
      amount NUMERIC(12,2) NOT NULL, currency TEXT NOT NULL DEFAULT 'CRC',
      status TEXT NOT NULL DEFAULT 'payment_pending' CHECK(status IN ('payment_pending','paid','failed','canceled','expired','refunded')),
      provider TEXT NOT NULL DEFAULT 'sandbox', provider_order_id TEXT, beta_code TEXT,
      beta_price BOOLEAN NOT NULL DEFAULT TRUE, consent_version TEXT NOT NULL,
      consent_at TIMESTAMPTZ NOT NULL, paid_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_billing_orders_status ON billing_orders(status,created_at DESC)""")
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
        order = conn.execute("""SELECT id,plan_code,amount,currency,status,created_at FROM billing_orders
          WHERE account_id=%s ORDER BY created_at DESC LIMIT 1""", (account_id,)).fetchone()
        subscription = conn.execute("SELECT * FROM billing_subscriptions WHERE account_id=%s", (account_id,)).fetchone()
        conn.commit()
    plans = []
    for code, info in PRICES.items():
        plans.append({"code": code, "beta_price_crc": info["beta"], "regular_price_crc": info["regular"],
                      "beta_months": 3, "slots_total": info["slots"], "slots_remaining": max(0, info["slots"] - used.get(code, 0))})
    return {"program": BETA_CODE, "plans": plans, "order": order, "subscription": subscription,
            "notice": "Precio beta por 3 meses; después aplica el precio regular indicado."}


def create_checkout(plan_code: str, accepted: bool, consent_version: str):
    if plan_code not in PRICES:
        raise HTTPException(400, "Plan de pago no válido.")
    if not accepted:
        raise HTTPException(422, "Debés aceptar las condiciones del precio beta.")
    account_id, workspace_id = get_current_account_id(), get_current_workspace_id()
    with get_connection() as conn:
        ensure_schema(conn)
        used = _counts(conn).get(plan_code, 0)
        if used >= PRICES[plan_code]["slots"]:
            raise HTTPException(409, "Los cupos beta de este plan están completos.")
        existing = conn.execute("""SELECT id,plan_code,amount,currency,status,created_at FROM billing_orders
          WHERE account_id=%s AND plan_code=%s AND status='payment_pending' ORDER BY created_at DESC LIMIT 1""", (account_id, plan_code)).fetchone()
        if existing:
            conn.commit()
            return {"status": "payment_pending", "order": existing,
                    "message": "Ya existe una solicitud pendiente para este plan."}
        order = conn.execute("""INSERT INTO billing_orders(account_id,workspace_id,plan_code,amount,beta_code,consent_version,consent_at)
          VALUES(%s,%s,%s,%s,%s,%s,NOW()) RETURNING id,plan_code,amount,currency,status,created_at""",
          (account_id, workspace_id, plan_code, PRICES[plan_code]["beta"], BETA_CODE, consent_version)).fetchone()
        conn.commit()
    record_event("checkout_started", "plan_selection")
    return {"status": "payment_pending", "order": order,
            "message": "Solicitud creada. El plan se activa únicamente después de confirmar el pago."}


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
        pending = conn.execute("""SELECT o.id,o.plan_code,o.amount,o.currency,o.created_at,a.primary_email AS email,a.display_name
          FROM billing_orders o JOIN accounts a ON a.id=o.account_id WHERE o.status='payment_pending' ORDER BY o.created_at""").fetchall()
        events = conn.execute("""SELECT event_name,COUNT(*) AS uses,COUNT(DISTINCT account_id) AS users
          FROM product_events WHERE created_at>=NOW()-INTERVAL '30 days' GROUP BY event_name ORDER BY uses DESC LIMIT 20""").fetchall()
        tickets = conn.execute("""SELECT f.id,f.category,f.subject,f.message,f.status,f.owner_notes,f.created_at,a.primary_email AS email
          FROM feedback_reports f JOIN accounts a ON a.id=f.account_id ORDER BY CASE f.status WHEN 'new' THEN 1 WHEN 'reviewing' THEN 2 ELSE 3 END,f.created_at DESC LIMIT 100""").fetchall()
        conn.commit()
    return {"beta": {code: {"used": used.get(code, 0), "total": info["slots"], "remaining": info["slots"]-used.get(code, 0)} for code, info in PRICES.items()},
            "pending_orders": pending, "feature_usage_30d": events,
            "tickets": [{**r, "public_id": f"FINVA-{int(r['id']):06d}"} for r in tickets]}


def resolve_test_order(order_id: int, action: str):
    with get_connection() as conn:
        ensure_schema(conn)
        order = conn.execute("SELECT * FROM billing_orders WHERE id=%s FOR UPDATE", (order_id,)).fetchone()
        if not order or order["status"] != "payment_pending":
            raise HTTPException(404, "Orden pendiente no encontrada.")
        if action == "reject":
            conn.execute("UPDATE billing_orders SET status='failed',updated_at=NOW() WHERE id=%s", (order_id,))
            conn.commit(); return {"status": "failed"}
        if _counts(conn).get(order["plan_code"], 0) >= PRICES[order["plan_code"]]["slots"]:
            raise HTTPException(409, "No quedan cupos beta.")
        conn.execute("UPDATE billing_orders SET status='paid',paid_at=NOW(),updated_at=NOW() WHERE id=%s", (order_id,))
        conn.execute("""INSERT INTO billing_subscriptions(account_id,workspace_id,plan_code,status,beta_code,beta_ends_at,current_period_start,current_period_end,paid_price_crc,regular_price_crc)
          VALUES(%s,%s,%s,'active',%s,NOW()+INTERVAL '3 months',NOW(),NOW()+INTERVAL '1 month',%s,%s)
          ON CONFLICT(account_id) DO UPDATE SET plan_code=EXCLUDED.plan_code,status='active',beta_code=EXCLUDED.beta_code,
          beta_ends_at=EXCLUDED.beta_ends_at,current_period_start=NOW(),current_period_end=EXCLUDED.current_period_end,
          paid_price_crc=EXCLUDED.paid_price_crc,regular_price_crc=EXCLUDED.regular_price_crc,updated_at=NOW()""",
          (order["account_id"], order["workspace_id"], order["plan_code"], BETA_CODE, order["amount"], PRICES[order["plan_code"]]["regular"]))
        plan = conn.execute("SELECT id FROM plans WHERE code=%s", (order["plan_code"],)).fetchone()
        conn.execute("""INSERT INTO account_subscriptions(account_id,plan_id,status,access_source,started_at,last_payment_at,created_at,updated_at)
          VALUES(%s,%s,'active','self_service',NOW(),NOW(),NOW(),NOW()) ON CONFLICT(account_id) DO UPDATE SET
          plan_id=EXCLUDED.plan_id,status='active',access_source='self_service',started_at=NOW(),last_payment_at=NOW(),updated_at=NOW()""", (order["account_id"], plan["id"]))
        conn.execute("UPDATE accounts SET plan_selected=TRUE,onboarding_completed=FALSE,updated_at=NOW() WHERE id=%s", (order["account_id"],))
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
