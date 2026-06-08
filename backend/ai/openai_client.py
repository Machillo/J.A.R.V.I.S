from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from typing import Any

import requests
from fastapi import HTTPException, status

from backend.auth.current_user import get_current_user
from backend.core.database import get_connection

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
OPENAI_MONTHLY_BUDGET_USD = float(os.getenv("OPENAI_MONTHLY_BUDGET_USD", "10") or 10)
OPENAI_INPUT_USD_PER_1M = float(os.getenv("OPENAI_INPUT_USD_PER_1M", "0.15") or 0.15)
OPENAI_OUTPUT_USD_PER_1M = float(os.getenv("OPENAI_OUTPUT_USD_PER_1M", "0.60") or 0.60)
OPENAI_OWNER_ONLY = os.getenv("OPENAI_OWNER_ONLY", "true").strip().lower() != "false"
OPENAI_TIMEOUT_SECONDS = int(os.getenv("OPENAI_TIMEOUT_SECONDS", "35") or 35)


def _is_owner(user: dict[str, Any] | None = None) -> bool:
    user = user or get_current_user()
    return user.get("role") in {"owner", "admin"}


def _estimate_tokens(text: str | None) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / 4) + 1)


def _estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    input_cost = (prompt_tokens / 1_000_000) * OPENAI_INPUT_USD_PER_1M
    output_cost = (completion_tokens / 1_000_000) * OPENAI_OUTPUT_USD_PER_1M
    return round(input_cost + output_cost, 6)


def ensure_openai_tables(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_premium_usage_events (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            provider TEXT NOT NULL DEFAULT 'openai',
            model TEXT NOT NULL,
            route TEXT NOT NULL DEFAULT 'jarvis',
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            estimated_cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_premium_guides (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            guide_type TEXT NOT NULL,
            title TEXT,
            content TEXT NOT NULL,
            data JSONB NOT NULL DEFAULT '{}'::jsonb,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_premium_settings (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL UNIQUE,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            monthly_budget_usd NUMERIC(12, 2) NOT NULL DEFAULT 10.00,
            warning_percent INTEGER NOT NULL DEFAULT 80,
            hard_stop_percent INTEGER NOT NULL DEFAULT 100,
            provider TEXT NOT NULL DEFAULT 'openai',
            model TEXT NOT NULL DEFAULT 'gpt-4o-mini',
            owner_only BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_premium_usage_user_month ON ai_premium_usage_events(user_id, created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ai_premium_guides_user ON ai_premium_guides(user_id, guide_type, is_active)")


def _json(data: Any) -> str:
    return json.dumps(data or {}, ensure_ascii=False)


def _current_month_bounds() -> tuple[str, str]:
    today = date.today()
    start = today.replace(day=1).isoformat()
    if today.month == 12:
        end = date(today.year + 1, 1, 1).isoformat()
    else:
        end = date(today.year, today.month + 1, 1).isoformat()
    return start, end


def _settings_for_user(conn, user_id: int) -> dict[str, Any]:
    ensure_openai_tables(conn)
    row = conn.execute(
        """
        INSERT INTO ai_premium_settings (user_id, enabled, monthly_budget_usd, model, owner_only)
        VALUES (%s, TRUE, %s, %s, %s)
        ON CONFLICT (user_id) DO UPDATE SET updated_at = ai_premium_settings.updated_at
        RETURNING *
        """,
        (user_id, OPENAI_MONTHLY_BUDGET_USD, OPENAI_MODEL, OPENAI_OWNER_ONLY),
    ).fetchone()
    return dict(row)


def get_openai_budget_status(user_id: int | None = None) -> dict[str, Any]:
    user = get_current_user()
    target_user_id = int(user_id or user["id"])
    if target_user_id != int(user["id"]) and not _is_owner(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No tienes permisos para ver este consumo.")

    start, end = _current_month_bounds()
    with get_connection() as conn:
        settings = _settings_for_user(conn, target_user_id)
        row = conn.execute(
            """
            SELECT
                COALESCE(SUM(estimated_cost_usd), 0) AS cost,
                COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                COALESCE(SUM(total_tokens), 0) AS total_tokens,
                COUNT(*) AS requests_count
            FROM ai_premium_usage_events
            WHERE user_id = %s
              AND created_at >= %s::date
              AND created_at < %s::date
            """,
            (target_user_id, start, end),
        ).fetchone()
        conn.commit()

    budget = float(settings.get("monthly_budget_usd") or OPENAI_MONTHLY_BUDGET_USD)
    used = float(row.get("cost") or 0)
    percent = round((used / budget) * 100, 2) if budget > 0 else 0
    return {
        "status": "OK",
        "enabled": bool(settings.get("enabled")) and bool(OPENAI_API_KEY),
        "configured": bool(OPENAI_API_KEY),
        "owner_only": bool(settings.get("owner_only")),
        "provider": settings.get("provider") or "openai",
        "model": settings.get("model") or OPENAI_MODEL,
        "month": start[:7],
        "budget_usd": budget,
        "used_usd": round(used, 6),
        "remaining_usd": round(max(budget - used, 0), 6),
        "percent_used": percent,
        "requests_count": int(row.get("requests_count") or 0),
        "prompt_tokens": int(row.get("prompt_tokens") or 0),
        "completion_tokens": int(row.get("completion_tokens") or 0),
        "total_tokens": int(row.get("total_tokens") or 0),
        "warning_percent": int(settings.get("warning_percent") or 80),
        "hard_stop_percent": int(settings.get("hard_stop_percent") or 100),
    }


def can_use_openai(estimated_prompt_tokens: int = 0) -> tuple[bool, dict[str, Any]]:
    user = get_current_user()
    if OPENAI_OWNER_ONLY and not _is_owner(user):
        return False, {"status": "OWNER_ONLY", "message": "ChatGPT está habilitado solo para owner."}
    if not OPENAI_API_KEY:
        return False, {"status": "MISSING_KEY", "message": "Falta OPENAI_API_KEY en Render."}

    status_payload = get_openai_budget_status(int(user["id"]))
    if not status_payload.get("enabled"):
        return False, {"status": "DISABLED", "message": "ChatGPT Premium está desactivado."}

    projected_cost = _estimate_cost(estimated_prompt_tokens, 500)
    if status_payload["used_usd"] + projected_cost >= status_payload["budget_usd"]:
        return False, {"status": "BUDGET_EXCEEDED", "message": "Presupuesto mensual de ChatGPT alcanzado.", "budget": status_payload}
    return True, status_payload


def _record_openai_usage(
    *,
    user_id: int,
    route: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    estimated_cost_usd: float,
) -> dict[str, Any]:
    with get_connection() as conn:
        ensure_openai_tables(conn)
        conn.execute(
            """
            INSERT INTO ai_premium_usage_events (
                user_id, provider, model, route,
                prompt_tokens, completion_tokens, total_tokens, estimated_cost_usd
            )
            VALUES (%s, 'openai', %s, %s, %s, %s, %s, %s)
            """,
            (user_id, model, route, prompt_tokens, completion_tokens, total_tokens, estimated_cost_usd),
        )
        conn.commit()
    return get_openai_budget_status(user_id)


def save_premium_guide(guide_type: str, title: str, content: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
    user = get_current_user()
    user_id = int(user["id"])
    with get_connection() as conn:
        ensure_openai_tables(conn)
        conn.execute(
            """
            UPDATE ai_premium_guides
            SET is_active = FALSE, updated_at = NOW()
            WHERE user_id = %s AND guide_type = %s AND is_active = TRUE
            """,
            (user_id, guide_type),
        )
        row = conn.execute(
            """
            INSERT INTO ai_premium_guides (user_id, guide_type, title, content, data)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            RETURNING *
            """,
            (user_id, guide_type, title, content, _json(data or {})),
        ).fetchone()
        conn.commit()
    return {"status": "OK", "guide": dict(row)}


def get_active_premium_guides(limit: int = 3) -> list[dict[str, Any]]:
    user = get_current_user()
    with get_connection() as conn:
        ensure_openai_tables(conn)
        rows = conn.execute(
            """
            SELECT id, guide_type, title, content, data, created_at
            FROM ai_premium_guides
            WHERE user_id = %s AND is_active = TRUE
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (int(user["id"]), limit),
        ).fetchall()
        conn.commit()
    return [dict(row) for row in rows]


def ask_openai(
    prompt: str,
    *,
    route: str = "jarvis_premium",
    system: str | None = None,
    max_tokens: int = 700,
    temperature: float = 0.25,
) -> dict[str, Any]:
    user = get_current_user()
    estimated_prompt = _estimate_tokens(prompt) + _estimate_tokens(system)
    allowed, budget = can_use_openai(estimated_prompt)
    if not allowed:
        return {"status": budget.get("status", "BLOCKED"), "message": budget.get("message"), "budget": budget.get("budget", budget)}

    model = budget.get("model") or OPENAI_MODEL
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=OPENAI_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        return {"status": "ERROR", "message": f"No pude conectar con OpenAI: {exc}"}

    if response.status_code >= 400:
        try:
            payload = response.json()
        except Exception:
            payload = {"error": response.text}
        return {"status": "ERROR", "message": "OpenAI devolvió error.", "error": payload}

    payload = response.json()
    text = (payload.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
    usage = payload.get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or estimated_prompt)
    completion_tokens = int(usage.get("completion_tokens") or _estimate_tokens(text))
    total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens))
    cost = _estimate_cost(prompt_tokens, completion_tokens)
    updated_budget = _record_openai_usage(
        user_id=int(user["id"]),
        route=route,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usd=cost,
    )

    return {
        "status": "OK",
        "text": text,
        "model": model,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "estimated_cost_usd": cost,
        },
        "budget": updated_budget,
    }
