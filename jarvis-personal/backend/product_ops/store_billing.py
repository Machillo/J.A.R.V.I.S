import os
from datetime import datetime, timezone

from fastapi import HTTPException

from backend.auth.current_user import get_current_account_id, get_current_workspace_id
from backend.core.database import get_connection
from backend.product_ops.service import record_event

# Store product identifiers stay configurable until the App Store / Play Console
# products are created. The backend remains the source of truth for entitlements.
PRODUCTS = {
    "basic": {
        "monthly": {"price_crc": 2990, "product_id": os.getenv("FINVA_BASIC_MONTHLY_PRODUCT_ID", "finva.basic.monthly")},
        "annual": {"price_crc": int(os.getenv("FINVA_BASIC_ANNUAL_CRC", "29900")), "product_id": os.getenv("FINVA_BASIC_ANNUAL_PRODUCT_ID", "finva.basic.annual")},
    },
    "vip": {
        "monthly": {"price_crc": 5990, "product_id": os.getenv("FINVA_VIP_MONTHLY_PRODUCT_ID", "finva.vip.monthly")},
        "annual": {"price_crc": int(os.getenv("FINVA_VIP_ANNUAL_CRC", "59900")), "product_id": os.getenv("FINVA_VIP_ANNUAL_PRODUCT_ID", "finva.vip.annual")},
    },
}
TRIAL_DAYS = int(os.getenv("FINVA_STORE_TRIAL_DAYS", "7"))
ACTIVE_STATES = {"trialing", "active", "grace_period"}


def ensure_store_schema(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS store_subscriptions (
      account_id UUID PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
      workspace_id UUID,
      provider TEXT NOT NULL CHECK(provider IN ('apple','google','sandbox')),
      plan_code TEXT NOT NULL CHECK(plan_code IN ('basic','vip')),
      billing_period TEXT NOT NULL CHECK(billing_period IN ('monthly','annual')),
      product_id TEXT NOT NULL,
      status TEXT NOT NULL CHECK(status IN ('trialing','active','grace_period','canceled','expired','revoked')),
      provider_subscription_id TEXT,
      original_transaction_id TEXT,
      trial_ends_at TIMESTAMPTZ,
      current_period_start TIMESTAMPTZ,
      current_period_end TIMESTAMPTZ,
      cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
      auto_renew BOOLEAN NOT NULL DEFAULT TRUE,
      pending_plan_code TEXT CHECK(pending_plan_code IS NULL OR pending_plan_code IN ('basic','vip')),
      pending_billing_period TEXT CHECK(pending_billing_period IS NULL OR pending_billing_period IN ('monthly','annual')),
      pending_product_id TEXT,
      pending_effective_at TIMESTAMPTZ,
      last_verified_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    conn.execute("ALTER TABLE store_subscriptions ADD COLUMN IF NOT EXISTS pending_plan_code TEXT")
    conn.execute("ALTER TABLE store_subscriptions ADD COLUMN IF NOT EXISTS pending_billing_period TEXT")
    conn.execute("ALTER TABLE store_subscriptions ADD COLUMN IF NOT EXISTS pending_product_id TEXT")
    conn.execute("ALTER TABLE store_subscriptions ADD COLUMN IF NOT EXISTS pending_effective_at TIMESTAMPTZ")
    conn.execute("""CREATE TABLE IF NOT EXISTS store_subscription_events (
      id BIGSERIAL PRIMARY KEY,
      account_id UUID REFERENCES accounts(id) ON DELETE SET NULL,
      provider TEXT NOT NULL,
      event_type TEXT NOT NULL,
      provider_event_id TEXT,
      plan_code TEXT,
      billing_period TEXT,
      effective_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      payload_hash TEXT,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())""")
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS uq_store_event_provider_id
      ON store_subscription_events(provider,provider_event_id) WHERE provider_event_id IS NOT NULL""")
    conn.execute("""CREATE INDEX IF NOT EXISTS idx_store_subscription_status
      ON store_subscriptions(status,current_period_end)""")
    for table in ("store_subscriptions", "store_subscription_events"):
        conn.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        conn.execute(f"REVOKE ALL PRIVILEGES ON TABLE {table} FROM anon, authenticated")


def store_catalog():
    return {
        "currency": "CRC",
        "trial_days": TRIAL_DAYS,
        "plans": [
            {
                "code": plan,
                "monthly": PRODUCTS[plan]["monthly"],
                "annual": PRODUCTS[plan]["annual"],
            }
            for plan in ("basic", "vip")
        ],
        "stores": {
            "apple": {"ready": bool(os.getenv("FINVA_APPLE_BUNDLE_ID")), "billing": "App Store"},
            "google": {"ready": bool(os.getenv("FINVA_GOOGLE_PACKAGE_NAME")), "billing": "Google Play"},
        },
    }


def _public_state(row):
    if not row:
        return {
            "plan": "free",
            "entitlement": "free",
            "status": "free",
            "provider": None,
            "billing_period": None,
            "trial_ends_at": None,
            "current_period_end": None,
            "cancel_at_period_end": False,
            "auto_renew": False,
            "pending_plan": None,
            "pending_billing_period": None,
            "pending_effective_at": None,
        }
    row = dict(row)
    period_end = row.get("current_period_end")
    if isinstance(period_end, str):
        try:
            period_end = datetime.fromisoformat(period_end.replace("Z", "+00:00"))
        except ValueError:
            period_end = None
    trial_end = row.get("trial_ends_at")
    if isinstance(trial_end, str):
        try:
            trial_end = datetime.fromisoformat(trial_end.replace("Z", "+00:00"))
        except ValueError:
            trial_end = None
    entitlement_end = trial_end if row["status"] == "trialing" else period_end
    active = row["status"] in ACTIVE_STATES and (
        entitlement_end is None or entitlement_end > datetime.now(timezone.utc)
    )
    return {
        "plan": row["plan_code"] if active else "free",
        "entitlement": row["plan_code"] if active else "free",
        "status": row["status"],
        "provider": row["provider"],
        "billing_period": row["billing_period"],
        "product_id": row["product_id"],
        "trial_ends_at": row.get("trial_ends_at"),
        "current_period_end": row.get("current_period_end"),
        "cancel_at_period_end": bool(row.get("cancel_at_period_end")),
        "auto_renew": bool(row.get("auto_renew")),
        "pending_plan": row.get("pending_plan_code"),
        "pending_billing_period": row.get("pending_billing_period"),
        "pending_effective_at": row.get("pending_effective_at"),
        "last_verified_at": row.get("last_verified_at"),
    }



def restore_owner_access():
    """Repair an owner account if a sandbox billing test overwrote its access."""
    account_id = get_current_account_id()
    with get_connection() as conn:
        vip = conn.execute("SELECT id FROM plans WHERE code='vip' AND is_active=TRUE", ()).fetchone()
        if not vip:
            raise HTTPException(404, "Plan VIP no disponible.")
        conn.execute(
            """INSERT INTO account_subscriptions(
                 account_id,plan_id,status,access_source,started_at,created_at,updated_at)
               VALUES(%s,%s,'active','owner',NOW(),NOW(),NOW())
               ON CONFLICT(account_id) DO UPDATE SET
                 plan_id=EXCLUDED.plan_id,status='active',access_source='owner',
                 expires_at=NULL,courtesy_note=NULL,granted_by=NULL,granted_at=NULL,updated_at=NOW()
               RETURNING account_id""",
            (account_id, vip["id"]),
        )
        conn.commit()
    return {"status": "restored", "plan": "vip", "access_source": "owner"}

def entitlement_state():
    account_id = get_current_account_id()
    with get_connection() as conn:
        ensure_store_schema(conn)
        row = conn.execute("SELECT * FROM store_subscriptions WHERE account_id=%s", (account_id,)).fetchone()
        conn.commit()
    return _public_state(row)


def _product(plan_code, billing_period):
    try:
        return PRODUCTS[plan_code][billing_period]
    except KeyError as exc:
        raise HTTPException(422, "Plan o periodo de facturación no válido.") from exc


def apply_store_event(account_id: str, workspace_id: str | None, plan_code: str, billing_period: str, event_type: str, *, provider: str = "sandbox"):
    """Apply an already-verified store lifecycle event.

    Authentication and provider verification belong to the caller. This is the
    shared state engine that sandbox QA and future Apple/Google handlers use.
    """
    product = _product(plan_code, billing_period)
    transitions = {
        "trial_started": ("trialing", False, True),
        "purchased": ("active", False, True),
        "renewed": ("active", False, True),
        "upgrade": ("active", False, True),
        "downgrade": ("active", False, True),
        "cancel_requested": ("active", True, False),
        "grace_period": ("grace_period", False, False),
        "restored": ("active", False, True),
        "expired": ("expired", False, False),
        "revoked": ("revoked", False, False),
    }
    if event_type not in transitions:
        raise HTTPException(422, "Evento de suscripción no válido.")
    status, cancel_at_end, auto_renew = transitions[event_type]
    period = "1 month" if billing_period == "monthly" else "1 year"
    trial_sql = f"NOW()+INTERVAL '{TRIAL_DAYS} days'" if event_type == "trial_started" else "NULL"
    with get_connection() as conn:
        ensure_store_schema(conn)
        target = conn.execute("SELECT id FROM accounts WHERE id=%s", (account_id,)).fetchone()
        if not target:
            raise HTTPException(404, "Cuenta objetivo no encontrada.")
        if event_type == "downgrade":
            existing_store = conn.execute(
                "SELECT * FROM store_subscriptions WHERE account_id=%s",
                (account_id,),
            ).fetchone()
            if not existing_store or existing_store["status"] not in ACTIVE_STATES:
                raise HTTPException(409, "No hay una suscripción activa para programar el downgrade.")
            if existing_store["plan_code"] != "vip" or plan_code != "basic":
                raise HTTPException(422, "El downgrade diferido soportado es VIP a Basic.")
            conn.execute(
                """UPDATE store_subscriptions SET
                     pending_plan_code=%s,pending_billing_period=%s,pending_product_id=%s,
                     pending_effective_at=current_period_end,last_verified_at=NOW(),updated_at=NOW()
                   WHERE account_id=%s
                   RETURNING account_id""",
                (plan_code, billing_period, product["product_id"], account_id),
            )
            conn.execute(
                """INSERT INTO store_subscription_events(account_id,provider,event_type,plan_code,billing_period)
                   VALUES(%s,%s,%s,%s,%s)
                   RETURNING id""",
                (account_id, provider, event_type, plan_code, billing_period),
            )
            row = conn.execute("SELECT * FROM store_subscriptions WHERE account_id=%s", (account_id,)).fetchone()
            conn.commit()
            return {"event": event_type, "target_account_id": account_id, "subscription": _public_state(row)}
        conn.execute(
            f"""INSERT INTO store_subscriptions(
              account_id,workspace_id,provider,plan_code,billing_period,product_id,status,
              trial_ends_at,current_period_start,current_period_end,cancel_at_period_end,
              auto_renew,last_verified_at,created_at,updated_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s,{trial_sql},NOW(),NOW()+INTERVAL '{period}',%s,%s,NOW(),NOW(),NOW())
            ON CONFLICT(account_id) DO UPDATE SET
              provider=EXCLUDED.provider,plan_code=EXCLUDED.plan_code,billing_period=EXCLUDED.billing_period,
              product_id=EXCLUDED.product_id,status=EXCLUDED.status,
              trial_ends_at=CASE WHEN %s IN ('cancel_requested','grace_period') THEN store_subscriptions.trial_ends_at ELSE EXCLUDED.trial_ends_at END,
              current_period_start=CASE
                WHEN %s IN ('cancel_requested','grace_period') THEN store_subscriptions.current_period_start
                WHEN %s='renewed' THEN GREATEST(COALESCE(store_subscriptions.current_period_end,NOW()),NOW())
                ELSE NOW()
              END,
              current_period_end=CASE
                WHEN %s IN ('cancel_requested','grace_period','expired','revoked') THEN store_subscriptions.current_period_end
                WHEN %s='renewed' THEN GREATEST(COALESCE(store_subscriptions.current_period_end,NOW()),NOW())+INTERVAL '{period}'
                ELSE EXCLUDED.current_period_end
              END,
              cancel_at_period_end=EXCLUDED.cancel_at_period_end,
              auto_renew=EXCLUDED.auto_renew,last_verified_at=NOW(),updated_at=NOW()\n            RETURNING account_id""",
            (account_id, workspace_id, provider, plan_code, billing_period, product["product_id"], status, cancel_at_end, auto_renew, event_type, event_type, event_type, event_type, event_type),
        )
        conn.execute(
            """INSERT INTO store_subscription_events(account_id,provider,event_type,plan_code,billing_period)
               VALUES(%s,%s,%s,%s,%s)
               RETURNING id""",
            (account_id, provider, event_type, plan_code, billing_period),
        )
        plan = conn.execute("SELECT id FROM plans WHERE code=%s AND is_active=TRUE", (plan_code,)).fetchone()
        if not plan:
            raise HTTPException(404, "Plan FINVA no disponible.")
        existing = conn.execute(
            "SELECT access_source FROM account_subscriptions WHERE account_id=%s",
            (account_id,),
        ).fetchone()
        protected_access = existing and existing.get("access_source") in {"owner", "courtesy"}

        # Store sandbox/real billing must never downgrade privileged or courtesy
        # access. Those grants are managed independently from store entitlement.
        if not protected_access:
            if status in ACTIVE_STATES:
                conn.execute("""INSERT INTO account_subscriptions(account_id,plan_id,status,access_source,started_at,created_at,updated_at)
                  VALUES(%s,%s,'active','self_service',NOW(),NOW(),NOW())
                  ON CONFLICT(account_id) DO UPDATE SET plan_id=EXCLUDED.plan_id,status='active',access_source='self_service',updated_at=NOW()
                  RETURNING account_id""",
                  (account_id, plan["id"]))
            else:
                free_plan = conn.execute("SELECT id FROM plans WHERE code='free' AND is_active=TRUE").fetchone()
                if free_plan:
                    conn.execute("""INSERT INTO account_subscriptions(account_id,plan_id,status,access_source,started_at,created_at,updated_at)
                      VALUES(%s,%s,'active','self_service',NOW(),NOW(),NOW())
                      ON CONFLICT(account_id) DO UPDATE SET plan_id=EXCLUDED.plan_id,status='active',access_source='self_service',updated_at=NOW()
                      RETURNING account_id""",
                      (account_id, free_plan["id"]))
        row = conn.execute("SELECT * FROM store_subscriptions WHERE account_id=%s", (account_id,)).fetchone()
        conn.commit()
    return {"event": event_type, "target_account_id": account_id, "subscription": _public_state(row)}


def simulate_lifecycle(plan_code: str, billing_period: str, event_type: str, *, target_account_id: str | None = None):
    """Owner-only QA adapter. Not part of the customer purchase flow."""
    actor_account_id = get_current_account_id()
    account_id = target_account_id or actor_account_id
    workspace_id = get_current_workspace_id() if not target_account_id else None
    return apply_store_event(account_id, workspace_id, plan_code, billing_period, event_type, provider="sandbox")
