from backend.core.database import get_connection


def get_allowed_users():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, email, role, status, created_at
            FROM allowed_users
            ORDER BY id ASC
            """
        ).fetchall()

    return [dict(row) for row in rows]

def create_allowed_user(email: str, role: str = "user", status: str = "active"):
    valid_roles = ["owner", "admin", "user", "viewer"]
    valid_statuses = ["active", "blocked", "pending"]

    if role not in valid_roles:
        return {
            "status": "ERROR",
            "message": "Rol inválido."
        }

    if status not in valid_statuses:
        return {
            "status": "ERROR",
            "message": "Estado inválido."
        }

    with get_connection() as conn:
        existing = conn.execute(
            """
            SELECT id
            FROM allowed_users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

        if existing:
            return {
                "status": "ERROR",
                "message": "Ese correo ya está autorizado."
            }

        cursor = conn.execute(
            """
            INSERT INTO allowed_users (
                email,
                role,
                status,
                created_at
            )
            VALUES (?, ?, ?, datetime('now'))
            """,
            (
                email.lower().strip(),
                role,
                status
            )
        )

        conn.commit()

    return {
        "message": "Usuario autorizado correctamente.",
        "id": cursor.lastrowid
    }

def delete_allowed_user(user_id: int):
    with get_connection() as conn:

        existing = conn.execute(
            """
            SELECT *
            FROM allowed_users
            WHERE id = ?
            """,
            (user_id,)
        ).fetchone()

        if not existing:
            return {
                "status": "ERROR",
                "message": "Usuario no encontrado."
            }

        if existing["role"] == "owner":
            return {
                "status": "ERROR",
                "message": "No se puede eliminar el owner."
            }

        conn.execute(
            """
            DELETE FROM allowed_users
            WHERE id = ?
            """,
            (user_id,)
        )

        conn.commit()

    return {
        "status": "OK",
        "message": "Usuario eliminado."
    }

def check_user_access(email: str):
    normalized_email = email.lower().strip()

    with get_connection() as conn:
        user = conn.execute(
            """
            SELECT id, email, role, status, created_at
            FROM allowed_users
            WHERE email = ?
            """,
            (normalized_email,)
        ).fetchone()

    if not user:
        return {
            "allowed": False,
            "message": "Correo no autorizado."
        }

    user_dict = dict(user)

    if user_dict["status"] != "active":
        return {
            "allowed": False,
            "message": "Usuario no activo.",
            "user": user_dict
        }

    return {
        "allowed": True,
        "message": "Acceso autorizado.",
        "user": user_dict
    }