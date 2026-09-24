import base64
import json
import os
import logging
import uuid
from typing import Any

import requests
from fastapi import HTTPException, status

from backend.core.database import get_connection
from backend.auth.workspace_context import resolve_personal_workspace_context, sync_account_auth_identity
from backend.auth.saas import enrich_identity


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_ADMIN_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SECRET_KEY")

VALID_ROLES = {"owner", "admin", "user", "viewer"}
VALID_STATUSES = {"active", "blocked", "pending"}
OWNER_EMAILS = {email.strip().lower() for email in os.getenv("OWNER_EMAILS", "").split(",") if email.strip()}
logger = logging.getLogger(__name__)

DELETION_STAGES = (
    "IDENTITY", "FK_CHECK", "MAIL_CREDENTIALS_DELETE", "ACCOUNT_DELETE", "LEGACY_DELETE",
    "SUPABASE_AUTH_DELETE", "COMMIT", "MAIL_TOKEN_REVOKE", "DONE",
)
GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


def _log_deletion(deletion_id: str, stage: str, status: str, **technical) -> None:
    """Structured deletion trace without identity, secrets or financial data."""
    safe = {key: value for key, value in technical.items() if value not in (None, "")}
    logger.info(
        "account_deletion deletion_id=%s stage=%s status=%s technical=%s",
        deletion_id, stage, status, safe,
    )


def _deletion_error_metadata(exc: Exception) -> dict[str, object]:
    metadata: dict[str, object] = {"error_type": type(exc).__name__}
    status_code = getattr(exc, "status_code", None)
    if status_code:
        metadata["http_status"] = status_code
    pgcode = getattr(exc, "pgcode", None)
    if pgcode:
        metadata["pgcode"] = pgcode
    diag = getattr(exc, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None) if diag else None
    if constraint_name:
        metadata["constraint"] = constraint_name
    return metadata


def _normalize_email(email: str) -> str:
    return email.lower().strip()


def _supabase_admin_headers(admin_key: str) -> dict[str, str]:
    """Build headers accepted by both legacy and current Supabase admin keys."""
    headers = {"apikey": admin_key}
    # Current sb_secret keys are opaque, not JWTs. Sending them as Bearer makes
    # Supabase reject the request with "Invalid JWT". Legacy service_role keys
    # still require the Authorization header.
    if not admin_key.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {admin_key}"
    return headers


def _serialize_allowed_user(row) -> dict[str, Any] | None:
    if not row:
        return None

    data = dict(row)
    return {
        "id": data.get("id"),
        "email": data.get("email"),
        "role": data.get("role"),
        "status": data.get("status"),
        "supabase_user_id": data.get("supabase_user_id"),
        "created_at": data.get("created_at"),
        "last_login_at": data.get("last_login_at"),
    }


# DINCR signs in only with OAuth (Google, Apple). The Supabase Email provider is
# still reachable with the public anon key, so a password or magic-link session
# must never become a DINCR identity (identities are keyed by email).
ALLOWED_AUTH_PROVIDERS = frozenset(
    item.strip().lower() for item in os.getenv("DINCR_AUTH_PROVIDERS", "google,apple").split(",") if item.strip()
)


NON_OAUTH_FIRST_FACTORS = frozenset({
    "password", "otp", "magiclink", "anonymous", "sso/saml", "email/signup", "invite", "recovery", "email_change", "web3",
})


def _jwt_claims(token: str) -> dict[str, Any]:
    """Read claims of a token Supabase has already verified; never used to trust a token."""
    try:
        payload = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (IndexError, ValueError, json.JSONDecodeError):
        return {}


def _oauth_identity_allowed(access_token: str, user: dict[str, Any]) -> bool:
    if user.get("is_anonymous"):
        return False
    methods = {str(item.get("method")) for item in _jwt_claims(access_token).get("amr") or [] if isinstance(item, dict)}
    # The first factor must be OAuth; a second factor (e.g. totp) may accompany it.
    if methods and ("oauth" not in methods or methods & NON_OAUTH_FIRST_FACTORS):
        return False
    # `provider` is only the user's first identity (e.g. "email" for a dashboard-created
    # user who later signs in with Google), so any linked allowed provider is enough.
    metadata = user.get("app_metadata") or {}
    linked = {str(item).lower() for item in metadata.get("providers") or [metadata.get("provider")] if item}
    return bool(linked & ALLOWED_AUTH_PROVIDERS)


def verify_supabase_token(access_token: str) -> dict[str, Any]:
    """
    Valida el access_token contra Supabase Auth.
    No confiamos en datos enviados por el frontend sin verificarlos.
    """
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Faltan SUPABASE_URL o SUPABASE_ANON_KEY en Render.",
        )

    response = requests.get(
        f"{SUPABASE_URL.rstrip('/')}/auth/v1/user",
        headers={
            "apikey": SUPABASE_ANON_KEY,
            "Authorization": f"Bearer {access_token}",
        },
        timeout=10,
    )

    if response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de Supabase inválido o expirado.",
        )

    payload = response.json()
    email = payload.get("email")
    supabase_user_id = payload.get("id")

    if not email or not supabase_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Supabase no devolvió email o id de usuario.",
        )

    if not _oauth_identity_allowed(access_token, payload):
        logger.warning("Rejected a non-OAuth Supabase session")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Iniciá sesión con Google o Apple.",
        )

    return {
        "supabase_user_id": supabase_user_id,
        "email": _normalize_email(email),
        "raw": payload,
    }


def get_allowed_users():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, email, role, status, supabase_user_id, created_at, last_login_at
            FROM allowed_users
            ORDER BY id ASC
            """
        ).fetchall()

    return [_serialize_allowed_user(row) for row in rows]


def get_allowed_user_by_email(email: str):
    normalized_email = _normalize_email(email)

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, email, role, status, supabase_user_id, created_at, last_login_at
            FROM allowed_users
            WHERE email = %s
            """,
            (normalized_email,),
        ).fetchone()

    return _serialize_allowed_user(row)


def create_allowed_user(email: str, role: str = "user", status: str = "active"):
    normalized_email = _normalize_email(email)

    # Owner is provisioned through trusted server configuration/database operations,
    # never through an administrative request body (including from an admin account).
    if role == "owner":
        raise HTTPException(status_code=403, detail="El rol owner no se asigna desde la API.")

    if role not in VALID_ROLES:
        return {
            "status": "ERROR",
            "message": "Rol inválido.",
        }

    if status not in VALID_STATUSES:
        return {
            "status": "ERROR",
            "message": "Estado inválido.",
        }

    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT id
            FROM allowed_users
            WHERE email = %s
            """,
            (normalized_email,),
        ).fetchone()

        if existing:
            return {
                "status": "ERROR",
                "message": "Ese correo ya está autorizado.",
            }

        cursor = conn.execute(
            """
            INSERT INTO allowed_users (
                email,
                role,
                status,
                created_at
            )
            VALUES (%s, %s, %s, NOW())
            """,
            (normalized_email, role, status),
        )

        conn.commit()

    return {
        "status": "OK",
        "message": "Usuario autorizado correctamente.",
        "id": cursor.lastrowid,
    }


def delete_allowed_user(user_id: int):
    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT *
            FROM allowed_users
            WHERE id = %s
            """,
            (user_id,),
        ).fetchone()

        if not existing:
            return {
                "status": "ERROR",
                "message": "Usuario no encontrado.",
            }

        if existing["role"] == "owner":
            return {
                "status": "ERROR",
                "message": "No se puede eliminar el owner.",
            }

        conn.execute(
            """
            DELETE FROM allowed_users
            WHERE id = %s
            """,
            (user_id,),
        )

        conn.commit()

    return {
        "status": "OK",
        "message": "Usuario eliminado.",
    }


def delete_current_account() -> dict[str, str]:
    """Permanently delete the authenticated account and its owned data.

    The database migration makes account/workspace ownership cascade. We stage
    the database cleanup in a transaction, remove Supabase Auth, and only then
    commit so an Auth error rolls the local cleanup back.
    """
    from backend.auth.current_user import get_current_user

    deletion_id = str(uuid.uuid4())
    stage = "IDENTITY"
    _log_deletion(deletion_id, stage, "STARTED")
    current = get_current_user()
    account_id = str(current.get("account_id") or "")
    auth_user_id = str(current.get("supabase_user_id") or "")
    allowed_user_id = int(current.get("id") or 0)
    email = _normalize_email(str(current.get("email") or ""))

    if not account_id or not auth_user_id or not allowed_user_id:
        _log_deletion(deletion_id, stage, "FAILED", error_type="IncompleteIdentity", http_status=401)
        raise HTTPException(status_code=401, detail={"message": "No pudimos identificar tu cuenta.", "deletion_id": deletion_id, "stage": stage})
    if not SUPABASE_URL or not SUPABASE_ADMIN_KEY:
        _log_deletion(deletion_id, stage, "FAILED", error_type="MissingServerConfiguration", http_status=503)
        raise HTTPException(
            status_code=503,
            detail={"message": "La eliminación de cuenta no está configurada todavía. Contactá a soporte.", "deletion_id": deletion_id, "stage": stage},
        )

    try:
        with get_connection() as conn:
            # Validate the request identity against the account row. Do not scan
            # every FK in the schema: a RESTRICT constraint belonging to another
            # account used to disable deletion globally for Free, Basic and VIP.
            identity = conn.execute(
                """SELECT legacy_allowed_user_id, supabase_user_id, primary_email
                   FROM accounts WHERE id=%s FOR UPDATE""",
                (account_id,),
            ).fetchone()
            if not identity:
                raise HTTPException(status_code=404, detail="La cuenta ya no existe.")
            if str(identity.get("supabase_user_id") or "") != auth_user_id:
                raise HTTPException(status_code=409, detail="La identidad de la cuenta no coincide. Volvé a iniciar sesión.")

            _log_deletion(deletion_id, stage, "COMPLETED")

            canonical_allowed_user_id = int(identity.get("legacy_allowed_user_id") or allowed_user_id)
            canonical_email = _normalize_email(str(identity.get("primary_email") or email))

            stage = "FK_CHECK"
            incompatible = conn.execute(
                """SELECT child.relname AS child_table, c.conname AS constraint_name
                   FROM pg_constraint c
                   JOIN pg_class child ON child.oid=c.conrelid
                   JOIN pg_namespace ns ON ns.oid=child.relnamespace
                   WHERE c.contype='f' AND ns.nspname='public'
                     AND c.confrelid IN ('public.accounts'::regclass, 'public.workspaces'::regclass, 'public.users'::regclass)
                     AND c.confdeltype NOT IN ('c','n')
                   ORDER BY child.relname,c.conname"""
            ).fetchall()
            _log_deletion(
                deletion_id, stage, "COMPLETED",
                incompatible_fk_count=len(incompatible),
                incompatible_constraints=[f"{row['child_table']}.{row['constraint_name']}" for row in incompatible],
            )

            stage = "MAIL_CREDENTIALS_DELETE"
            # Vault secrets do not cascade from accounts. Read the Google tokens
            # so they can be revoked after commit, then drop every stored
            # mail credential inside the same transaction as the account.
            mail_credentials = conn.execute(
                """SELECT c.refresh_token_secret_id, c.granted_scopes, s.decrypted_secret
                   FROM finva_gmail_connections c
                   LEFT JOIN vault.decrypted_secrets s ON s.id=c.refresh_token_secret_id
                   WHERE c.account_id=%s""",
                (account_id,),
            ).fetchall()
            # A mailbox authorized but not yet attached keeps its token on the OAuth flow.
            flows_table = conn.execute("SELECT to_regclass('public.mail_oauth_flows') AS present").fetchone()
            if flows_table and flows_table.get("present"):
                mail_credentials = list(mail_credentials) + list(conn.execute(
                    """SELECT f.pending_secret_id AS refresh_token_secret_id, f.granted_scopes, s.decrypted_secret
                       FROM mail_oauth_flows f
                       LEFT JOIN vault.decrypted_secrets s ON s.id=f.pending_secret_id
                       WHERE f.account_id=%s AND f.pending_secret_id IS NOT NULL""",
                    (account_id,),
                ).fetchall())
            secret_ids =[str(row["refresh_token_secret_id"]) for row in mail_credentials if row.get("refresh_token_secret_id")]
            google_tokens = [
                str(row["decrypted_secret"]) for row in mail_credentials
                if row.get("decrypted_secret") and GMAIL_SCOPE in (row.get("granted_scopes") or [])
            ]
            if secret_ids:
                conn.execute("DELETE FROM vault.secrets WHERE id = ANY(%s::uuid[])", (secret_ids,))
            _log_deletion(deletion_id, stage, "COMPLETED", secrets_deleted=len(secret_ids))

            stage = "ACCOUNT_DELETE"
            deleted = conn.execute(
                "DELETE FROM accounts WHERE id=%s RETURNING id",
                (account_id,),
            ).fetchone()
            if not deleted:
                raise HTTPException(status_code=404, detail="La cuenta ya no existe.")
            _log_deletion(deletion_id, stage, "COMPLETED")

            stage = "LEGACY_DELETE"
            # Some historical finance rows use users.id. The workspace cascade
            # removes their data. Production users is keyed by email and does
            # not have the stale schema.sql allowed_user_id column.
            conn.execute("DELETE FROM users WHERE lower(email)=lower(%s)", (canonical_email,))
            conn.execute("DELETE FROM allowed_users WHERE id=%s", (canonical_allowed_user_id,))
            _log_deletion(deletion_id, stage, "COMPLETED")

            stage = "SUPABASE_AUTH_DELETE"
            response = requests.delete(
                f"{SUPABASE_URL.rstrip('/')}/auth/v1/admin/users/{auth_user_id}",
                headers=_supabase_admin_headers(SUPABASE_ADMIN_KEY),
                timeout=10,
            )
            if response.status_code not in {200, 204, 404}:
                _log_deletion(deletion_id, stage, "FAILED", error_type="SupabaseAdminResponse", http_status=response.status_code)
                raise HTTPException(
                    status_code=502,
                    detail="No pudimos eliminar tu acceso en este momento. El intento quedó registrado; probá nuevamente o contactá a soporte.",
                )
            _log_deletion(deletion_id, stage, "COMPLETED", http_status=response.status_code)

            stage = "COMMIT"
            conn.commit()
            _log_deletion(deletion_id, stage, "COMPLETED")
    except HTTPException as exc:
        _log_deletion(deletion_id, stage, "FAILED", **_deletion_error_metadata(exc))
        message = exc.detail if isinstance(exc.detail, str) else "No pudimos completar la eliminación."
        raise HTTPException(
            status_code=exc.status_code,
            detail={"message": message, "deletion_id": deletion_id, "stage": stage},
        ) from exc
    except Exception as exc:
        _log_deletion(deletion_id, stage, "FAILED", **_deletion_error_metadata(exc))
        logger.exception("Account deletion failed deletion_id=%s stage=%s", deletion_id, stage)
        raise HTTPException(
            status_code=500,
            detail={
                "message": "No pudimos completar la eliminación. Tus datos permanecen protegidos; intentá nuevamente o contactá a soporte.",
                "deletion_id": deletion_id,
                "stage": stage,
            },
        ) from exc

    stage = "MAIL_TOKEN_REVOKE"
    # Best effort after commit: the account is already gone and the secrets are
    # deleted, so a Google outage must not turn a completed deletion into an error.
    revoked = 0
    for google_token in google_tokens:
        try:
            response = requests.post("https://oauth2.googleapis.com/revoke", params={"token": google_token}, timeout=10)
            revoked += int(response.status_code in {200, 400})
        except Exception:
            pass
    _log_deletion(deletion_id, stage, "COMPLETED", google_tokens=len(google_tokens), revoked=revoked)

    stage = "DONE"
    _log_deletion(deletion_id, stage, "COMPLETED")
    return {"status": "OK", "message": "Cuenta eliminada permanentemente.", "deletion_id": deletion_id}


def check_user_access(email: str):
    user = get_allowed_user_by_email(email)

    if not user:
        return {
            "allowed": False,
            "message": "Correo no autorizado.",
        }

    if user["status"] != "active":
        return {
            "allowed": False,
            "message": "Usuario no activo.",
            "user": user,
        }

    return {
        "allowed": True,
        "message": "Acceso autorizado.",
        "user": user,
    }


def authenticate_access_token(access_token: str) -> dict[str, Any]:
    supabase_user = verify_supabase_token(access_token)
    app_user = get_allowed_user_by_email(supabase_user["email"])

    # Unified JARVIS: a valid Google/Supabase identity gets its own account + Personal workspace.
    # allowed_users remains only as the temporary legacy bridge required by older Personal tables.
    if not app_user:
        with get_connection() as conn:
            legacy = conn.execute(
                """INSERT INTO allowed_users(email,role,status,supabase_user_id,created_at,last_login_at)
                   VALUES(%s,'user','active',%s,NOW(),NOW())""",
                (supabase_user["email"], supabase_user["supabase_user_id"]),
            ).fetchone()
            legacy_id = int(legacy["id"])
            account = conn.execute(
                """INSERT INTO accounts(legacy_allowed_user_id,supabase_user_id,primary_email,display_name,role,status,created_at,updated_at,last_login_at)
                   VALUES(%s,%s,%s,%s,'user','active',NOW(),NOW(),NOW())""",
                (legacy_id, supabase_user["supabase_user_id"], supabase_user["email"], (supabase_user.get("raw") or {}).get("user_metadata", {}).get("full_name")),
            ).fetchone()
            account_id = str(account["id"])
            workspace = conn.execute(
                """INSERT INTO workspaces(workspace_key,owner_account_id,name,workspace_type,status,created_at,updated_at)
                   VALUES(%s,%s,%s,'personal','active',NOW(),NOW())""",
                (f"personal:{account_id}", account_id, f"{supabase_user['email']} Personal"),
            ).fetchone()
            conn.execute(
                """INSERT INTO workspace_members(workspace_id,account_id,member_role,status,created_at,updated_at)
                   VALUES(%s,%s,'owner','active',NOW(),NOW())""",
                (workspace["id"], account_id),
            )
            conn.commit()
        app_user = get_allowed_user_by_email(supabase_user["email"])

    if app_user["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tu usuario no está activo.",
        )

    effective_role = "owner" if app_user["email"] in OWNER_EMAILS else app_user["role"]

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE allowed_users
            SET supabase_user_id = %s,
                role = %s,
                last_login_at = NOW()
            WHERE id = %s
            """,
            (supabase_user["supabase_user_id"], effective_role, app_user["id"]),
        )
        sync_account_auth_identity(
            conn,
            legacy_allowed_user_id=int(app_user["id"]),
            supabase_user_id=supabase_user["supabase_user_id"],
            effective_role=effective_role,
        )
        workspace_context = resolve_personal_workspace_context(conn, int(app_user["id"]))
        conn.commit()

    return enrich_identity({
        "id": app_user["id"],
        "email": app_user["email"],
        "role": effective_role,
        "status": app_user["status"],
        "supabase_user_id": supabase_user["supabase_user_id"],
        **workspace_context,
    })
