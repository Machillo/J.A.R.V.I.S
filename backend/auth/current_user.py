from contextvars import ContextVar
from typing import Any, Optional

from fastapi import HTTPException, Request, status


_current_user: ContextVar[Optional[dict[str, Any]]] = ContextVar(
    "current_user",
    default=None,
)


def set_current_user(user: Optional[dict[str, Any]]):
    """
    Guarda el usuario autenticado solo durante el request actual.
    Esto permite que los servicios sigan usando get_current_user_id()
    sin pasar user_id manualmente por cada función.
    """
    return _current_user.set(user)


def reset_current_user(token) -> None:
    _current_user.reset(token)


def get_current_user() -> dict[str, Any]:
    user = _current_user.get()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No hay usuario autenticado en este request.",
        )

    return user


def get_current_user_id() -> int:
    return int(get_current_user()["id"])


def require_roles(*allowed_roles: str):
    user = get_current_user()
    role = user.get("role")

    if role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para realizar esta acción.",
        )

    return user


def get_current_user_from_request(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "user", None)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No hay usuario autenticado.",
        )

    return user
