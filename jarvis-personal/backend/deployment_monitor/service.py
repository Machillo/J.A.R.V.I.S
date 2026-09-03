from __future__ import annotations

from typing import Any

from backend.core.database import get_connection
from backend.notifications.service import send_system_push


FAILURE_STATES = {"failure", "failed", "error", "canceled", "cancelled", "server_failed", "image_pull_failed"}
SUCCESS_STATES = {"success", "succeeded", "ready"}


def ensure_deployment_table(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS deployment_events (
            id BIGSERIAL PRIMARY KEY,
            provider TEXT NOT NULL,
            external_id TEXT NOT NULL,
            service_name TEXT,
            event_type TEXT,
            status TEXT NOT NULL,
            commit_sha TEXT,
            summary TEXT,
            detail TEXT,
            log_url TEXT,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(provider, external_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deployment_events_created ON deployment_events(created_at DESC)")


def _normalized_status(value: Any, event_type: str = "") -> str:
    status = str(value or event_type or "unknown").lower()
    if status in FAILURE_STATES or event_type in FAILURE_STATES:
        return "failure"
    if status in SUCCESS_STATES:
        return "success"
    if status in {"pending", "queued", "building", "in_progress", "deploy_started", "build_started"}:
        return "pending"
    return status


def parse_event(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    provider = provider.lower().strip()
    if provider == "render":
        data = payload.get("data") or {}
        event_type = str(payload.get("type") or "render_event")
        external_id = str(data.get("id") or payload.get("id") or "")
        status = _normalized_status(data.get("status"), event_type)
        return {
            "provider": "render", "external_id": external_id,
            "service_name": data.get("serviceName") or data.get("serviceId") or "Render",
            "event_type": event_type, "status": status,
            "commit_sha": data.get("commitId") or data.get("commit_sha"),
            "summary": f"{event_type.replace('_', ' ').title()}: {status}",
            "detail": data.get("message") or data.get("reason"),
            "log_url": data.get("url") or data.get("logUrl"),
        }

    workflow = payload.get("workflow_run") or payload.get("check_run") or {}
    if workflow:
        state = workflow.get("conclusion") or workflow.get("status") or "unknown"
        sha = workflow.get("head_sha")
        return {
            "provider": "github", "external_id": str(workflow.get("id") or f"{sha}:{state}"),
            "service_name": workflow.get("name") or "JARVIS CI", "event_type": "ci_check",
            "status": _normalized_status(state), "commit_sha": sha,
            "summary": workflow.get("display_title") or workflow.get("name") or f"CI: {state}",
            "detail": workflow.get("conclusion"),
            "log_url": workflow.get("html_url") or workflow.get("details_url"),
        }

    status_data = payload.get("deployment_status") or {}
    deployment = payload.get("deployment") or {}
    context = payload.get("context") or status_data.get("environment") or "Vercel"
    state = payload.get("state") or status_data.get("state") or "unknown"
    sha = payload.get("sha") or deployment.get("sha")
    external_id = str(payload.get("id") or status_data.get("id") or f"{sha}:{context}:{state}")
    return {
        "provider": "vercel" if "vercel" in str(context).lower() else "github",
        "external_id": external_id, "service_name": str(context),
        "event_type": "deployment_status", "status": _normalized_status(state),
        "commit_sha": sha,
        "summary": payload.get("description") or status_data.get("description") or f"{context}: {state}",
        "detail": payload.get("error") or status_data.get("error"),
        "log_url": payload.get("target_url") or status_data.get("log_url") or status_data.get("environment_url"),
    }


def save_event(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    event = parse_event(provider, payload)
    if not event["external_id"]:
        raise ValueError("El evento no incluye un identificador estable.")
    with get_connection() as conn:
        ensure_deployment_table(conn)
        row = conn.execute(
            """
            INSERT INTO deployment_events
                (provider, external_id, service_name, event_type, status, commit_sha, summary, detail, log_url, payload)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (provider, external_id) DO UPDATE SET
                status=EXCLUDED.status, commit_sha=EXCLUDED.commit_sha, summary=EXCLUDED.summary,
                detail=EXCLUDED.detail, log_url=EXCLUDED.log_url, payload=EXCLUDED.payload, updated_at=NOW()
            RETURNING *
            """,
            (event["provider"], event["external_id"], event["service_name"], event["event_type"],
             event["status"], event["commit_sha"], event["summary"], event["detail"],
             event["log_url"], __import__("json").dumps(payload)),
        ).fetchone()
        conn.commit()
    if event["status"] == "failure":
        sha = str(event.get("commit_sha") or "")[:7]
        send_system_push("Falló un despliegue", f"{event['service_name']} · {sha or 'sin commit'} · {event['summary']}", "deployment", "/settings")
    return row


def deployment_summary(limit: int = 30) -> dict[str, Any]:
    with get_connection() as conn:
        ensure_deployment_table(conn)
        rows = conn.execute("SELECT * FROM deployment_events ORDER BY created_at DESC LIMIT %s", (max(1, min(limit, 100)),)).fetchall()
        conn.commit()
    latest = {}
    for row in rows:
        latest.setdefault(row["provider"], row)
    return {"status": "OK", "latest": latest, "events": rows}
