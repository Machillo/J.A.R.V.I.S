"""One-time, human-run PostHog baseline: new DINCR accounts per day.

Only aggregates leave the database: one ``baseline_daily_signups`` event per
day with a ``count``. No account id, email, plan or anything per user is sent.
The account creation date is the only history DINCR can reconstruct exactly.
Activity, plan at signup and mailbox history are NOT backfilled: an account
existing since June does not prove it was active, and mailbox ``connected_at``
changes on every reconnection. Those metrics start with the live events.

Known limit: accounts deleted before the backfill are not counted.

Idempotent: each day's event has a deterministic uuid and timestamp, so a
re-run produces the same events (PostHog deduplicates identical events).

    python -m backend.scripts.posthog_signups_baseline            # dry run: prints the aggregates
    python -m backend.scripts.posthog_signups_baseline --send     # sends them (needs POSTHOG_API_KEY/HOST)

Run it once, after the analytics release, from a trusted machine with read access
to the production database. It never writes to the database.
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import date

import requests

from backend.core.database import get_connection
from backend.product_ops.posthog_events import _configuration, safe_server_properties

EVENT = "baseline_daily_signups"
NAMESPACE = uuid.UUID("5d2f0f4e-2f3c-4b6e-9f3a-6c1e0d7b9a11")
QUERY = """SELECT (created_at AT TIME ZONE 'America/Costa_Rica')::date AS day, COUNT(*) AS total
           FROM accounts WHERE role <> 'owner' AND created_at < date_trunc('day', NOW())
           GROUP BY 1 ORDER BY 1"""


def daily_signups(conn) -> list[tuple[date, int]]:
    return [(row["day"], int(row["total"])) for row in conn.execute(QUERY).fetchall()]


def baseline_events(days: list[tuple[date, int]]) -> list[dict]:
    """One deterministic, aggregate-only event per day."""
    return [{
        "event": EVENT,
        "uuid": str(uuid.uuid5(NAMESPACE, f"{EVENT}:{day.isoformat()}")),
        "distinct_id": "dincr_baseline",
        "timestamp": f"{day.isoformat()}T12:00:00-06:00",
        "properties": {
            **safe_server_properties(EVENT, {"count": total}),
            "source_type": "backfill", "environment": "production",
            "$process_person_profile": False, "$geoip_disable": True,
        },
    } for day, total in days if total > 0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--send", action="store_true", help="send the aggregates to PostHog (default: dry run)")
    args = parser.parse_args(argv)
    with get_connection() as conn:
        events = baseline_events(daily_signups(conn))
    for event in events:
        print(event["timestamp"][:10], event["properties"]["count"])
    if not args.send:
        print(f"Dry run: {len(events)} daily aggregates. Nothing was sent.")
        return 0
    configuration = _configuration()
    if not configuration:
        print("POSTHOG_API_KEY/POSTHOG_HOST are not configured.", file=sys.stderr)
        return 1
    key, host = configuration
    for start in range(0, len(events), 100):
        requests.post(f"{host}/batch/", json={"api_key": key, "batch": events[start:start + 100]}, timeout=10).raise_for_status()
    print(f"Sent {len(events)} daily aggregates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
