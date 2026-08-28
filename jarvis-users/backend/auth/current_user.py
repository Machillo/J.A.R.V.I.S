from contextvars import ContextVar
from typing import Any

from fastapi import HTTPException, status


_current_user: ContextVar[dict[str, Any] | None] = ContextVar("current_user", default=None)


def set_current_user(user: dict[str, Any] | None):
    return _current_user.set(user)


def reset_current_user(token) -> None:
    _current_user.reset(token)


def get_current_user() -> dict[str, Any]:
    user = _current_user.get()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No hay usuario autenticado.")
    return user


def get_current_user_id() -> int:
    return int(get_current_user()["id"])
