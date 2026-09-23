from __future__ import annotations

from fastapi import HTTPException, Request

from backend.auth.current_user import get_current_account_id
from backend.core.database import get_connection


TERMS_VERSION = "2026-09-23-v3"
PRIVACY_VERSION = "2026-09-23-v3"


def ensure_legal_schema(conn) -> None:
    conn.execute(
        """CREATE TABLE IF NOT EXISTS legal_acceptances (
          id BIGSERIAL PRIMARY KEY,
          account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
          terms_version TEXT NOT NULL,
          privacy_version TEXT NOT NULL,
          terms_accepted_at TIMESTAMPTZ NOT NULL,
          privacy_accepted_at TIMESTAMPTZ NOT NULL,
          ip_address TEXT,
          user_agent TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
          UNIQUE(account_id,terms_version,privacy_version)
        )"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_legal_acceptances_account ON legal_acceptances(account_id,created_at DESC)"
    )
    # Legal evidence is written and read only by the authenticated backend.
    conn.execute("ALTER TABLE legal_acceptances ENABLE ROW LEVEL SECURITY")
    conn.execute("REVOKE ALL PRIVILEGES ON TABLE legal_acceptances FROM anon, authenticated")


def legal_status(conn, account_id: str) -> dict:
    ensure_legal_schema(conn)
    row = conn.execute(
        """SELECT terms_accepted_at,privacy_accepted_at
           FROM legal_acceptances
           WHERE account_id=%s AND terms_version=%s AND privacy_version=%s
           ORDER BY created_at DESC LIMIT 1""",
        (account_id, TERMS_VERSION, PRIVACY_VERSION),
    ).fetchone()
    return {
        "required": row is None,
        "terms_version": TERMS_VERSION,
        "privacy_version": PRIVACY_VERSION,
        "accepted_at": (row or {}).get("terms_accepted_at"),
    }


def accept_legal_documents(payload, request: Request) -> dict:
    if not payload.accept_terms or not payload.accept_privacy:
        raise HTTPException(422, "Debés aceptar los Términos y la Política de Privacidad para continuar.")
    if payload.terms_version != TERMS_VERSION or payload.privacy_version != PRIVACY_VERSION:
        raise HTTPException(409, "Los documentos cambiaron. Leé y aceptá la versión vigente.")

    forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
    ip_address = forwarded or (request.client.host if request.client else None)
    user_agent = request.headers.get("user-agent", "")[:500] or None
    account_id = get_current_account_id()
    with get_connection() as conn:
        ensure_legal_schema(conn)
        conn.execute(
            """INSERT INTO legal_acceptances(
                 account_id,terms_version,privacy_version,terms_accepted_at,privacy_accepted_at,ip_address,user_agent
               ) VALUES(%s,%s,%s,NOW(),NOW(),%s,%s)
               ON CONFLICT(account_id,terms_version,privacy_version) DO NOTHING""",
            (account_id, TERMS_VERSION, PRIVACY_VERSION, ip_address, user_agent),
        )
        conn.commit()
        return {"status": "accepted", **legal_status(conn, account_id)}
