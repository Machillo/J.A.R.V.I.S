"""Aggregate DINCR server events. No user, workspace or financial payloads."""

import logging
import os
import uuid
from urllib.parse import urlsplit

import requests

logger = logging.getLogger(__name__)
SERVER_EVENTS = frozenset({"gmail_connected", "account_deletion_completed"})
HOSTS = frozenset({"us.i.posthog.com", "eu.i.posthog.com"})


def capture_backend_event(event_name: str) -> None:
    """Fire a bounded, best-effort request from FastAPI BackgroundTasks."""
    key = os.getenv("POSTHOG_API_KEY", "").strip()
    host = os.getenv("POSTHOG_HOST", "").strip().rstrip("/")
    parsed = urlsplit(host)
    if (not key or event_name not in SERVER_EVENTS or parsed.scheme != "https"
            or parsed.netloc not in HOSTS or parsed.path or parsed.query or parsed.fragment):
        return
    try:
        response = requests.post(
            f"{host}/capture/",
            json={
                "api_key": key,
                "event": event_name,
                # Fresh per event: no account identifier or durable person profile.
                # $process_person_profile=False stops PostHog from creating a person
                # for each random id; the request IP is Render's, not the user's.
                "distinct_id": f"dincr_server_{uuid.uuid4().hex}",
                "properties": {
                    "success": True,
                    "source_type": "server",
                    "$process_person_profile": False,
                    "$geoip_disable": True,
                },
            },
            timeout=(0.5, 1.5),
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.warning("DINCR aggregate analytics unavailable")
