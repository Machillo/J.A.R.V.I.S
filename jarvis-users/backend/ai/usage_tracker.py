from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import HTTPException, status

from backend.auth.current_user import get_current_user
from backend.core.database import get_connection

DEFAULT_DAILY_LIMITS = {
    "owner": 250000,
    "admin": 80000,
    "user": 12000,
    "viewer": 3000,
}


def estimate_tokens(text: str | None) -> int:
    """Aproximación simple y suficiente para controlar consumo diario."""
    if not text:
        return 0
    return max(1, int(len(text) / 4) + 1)


def _ensure_usage_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_usage_daily (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            usage_date DATE NOT NULL,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            response_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            requests_count INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, usage_date)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_usage_events (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            usage_date DATE NOT NULL,
            route TEXT,
            model TEXT,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            response_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_usage_limits (
            id BIGSERIAL PRIMARY KEY,
            role TEXT NOT NULL UNIQUE,
            daily_token_limit INTEGER NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    for role, limit in DEFAULT_DAILY_LIMITS.items():
        conn.execute(
            """
            INSERT INTO ai_usage_limits (role, daily_token_limit)
            VALUES (%s, %s)
            ON CONFLICT (role)
            DO NOTHING
            """,
            (role, limit),
        )


def get_daily_limit_for_role(role: str) -> int:
    with get_connection() as conn:
        _ensure_usage_tables(conn)
        row = conn.execute(
            """
            SELECT daily_token_limit
            FROM ai_usage_limits
            WHERE role = %s
            """,
            (role,),
        ).fetchone()
        conn.commit()

    return int(row["daily_token_limit"]) if row else DEFAULT_DAILY_LIMITS.get(role, 5000)


def get_today_usage(user_id: int | None = None) -> dict[str, Any]:
    user = get_current_user()
    target_user_id = int(user_id or user["id"])

    if target_user_id != int(user["id"]) and user.get("role") not in {"owner", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos para ver el consumo de otro usuario.",
        )

    with get_connection() as conn:
        _ensure_usage_tables(conn)
        row = conn.execute(
            """
            SELECT prompt_tokens, response_tokens, total_tokens, requests_count
            FROM ai_usage_daily
            WHERE user_id = %s
            AND usage_date = CURRENT_DATE
            """,
            (target_user_id,),
        ).fetchone()
        conn.commit()

    role = user.get("role", "user") if target_user_id == int(user["id"]) else "user"
    limit = get_daily_limit_for_role(role)
    used = int(row["total_tokens"]) if row else 0

    return {
        "user_id": target_user_id,
        "date": date.today().isoformat(),
        "prompt_tokens": int(row["prompt_tokens"]) if row else 0,
        "response_tokens": int(row["response_tokens"]) if row else 0,
        "total_tokens": used,
        "requests_count": int(row["requests_count"]) if row else 0,
        "daily_limit": limit,
        "remaining_tokens": max(limit - used, 0),
        "percent_used": round((used / limit) * 100, 2) if limit else 0,
    }


def assert_can_use_ai(estimated_prompt_tokens: int = 0) -> dict[str, Any]:
    user = get_current_user()
    usage = get_today_usage(int(user["id"]))
    role = user.get("role", "user")

    if role in {"owner", "admin"}:
        return usage

    if usage["total_tokens"] + estimated_prompt_tokens > usage["daily_limit"]:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Límite diario de IA alcanzado para este usuario.",
        )

    return usage


def record_ai_usage(prompt: str, response: str, route: str = "jarvis", model: str | None = None) -> dict[str, Any]:
    user = get_current_user()
    user_id = int(user["id"])
    prompt_tokens = estimate_tokens(prompt)
    response_tokens = estimate_tokens(response)
    total_tokens = prompt_tokens + response_tokens

    with get_connection() as conn:
        _ensure_usage_tables(conn)
        conn.execute(
            """
            INSERT INTO ai_usage_events (
                user_id, usage_date, route, model,
                prompt_tokens, response_tokens, total_tokens
            )
            VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, %s)
            """,
            (user_id, route, model, prompt_tokens, response_tokens, total_tokens),
        )
        conn.execute(
            """
            INSERT INTO ai_usage_daily (
                user_id, usage_date, prompt_tokens, response_tokens, total_tokens, requests_count
            )
            VALUES (%s, CURRENT_DATE, %s, %s, %s, 1)
            ON CONFLICT (user_id, usage_date)
            DO UPDATE SET
                prompt_tokens = ai_usage_daily.prompt_tokens + EXCLUDED.prompt_tokens,
                response_tokens = ai_usage_daily.response_tokens + EXCLUDED.response_tokens,
                total_tokens = ai_usage_daily.total_tokens + EXCLUDED.total_tokens,
                requests_count = ai_usage_daily.requests_count + 1,
                updated_at = NOW()
            """,
            (user_id, prompt_tokens, response_tokens, total_tokens),
        )
        conn.commit()

    return get_today_usage(user_id)


def get_admin_usage_overview() -> dict[str, Any]:
    user = get_current_user()
    if user.get("role") not in {"owner", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Solo administradores pueden ver el consumo general.",
        )

    with get_connection() as conn:
        _ensure_usage_tables(conn)
        rows = conn.execute(
            """
            SELECT
                au.id AS user_id,
                au.email,
                au.role,
                COALESCE(u.total_tokens, 0) AS total_tokens,
                COALESCE(u.requests_count, 0) AS requests_count,
                COALESCE(l.daily_token_limit, 0) AS daily_limit
            FROM profiles au
            LEFT JOIN ai_usage_daily u
                ON u.user_id = au.id AND u.usage_date = CURRENT_DATE
            LEFT JOIN ai_usage_limits l
                ON l.role = au.role
            ORDER BY au.role, au.email
            """
        ).fetchall()
        conn.commit()

    return {"date": date.today().isoformat(), "users": [dict(row) for row in rows]}
