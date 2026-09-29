"""EXPERIMENT 003: what DINCR's own code does when a dependency fails.

Runs real backend functions under simulated failures and records the outcome
(the error class and status the caller would see). Useful for UX copy and
observability; nothing leaves the machine.
"""
from __future__ import annotations

from labs import chaos, db, email_lab, runtime, seed, synthetic


def _outcome(fn) -> str:
    try:
        result = fn()
        return f"ok: {result!r}"[:120]
    except Exception as exc:  # the experiment records every failure mode
        status = getattr(exc, "status_code", None)
        return f"{type(exc).__name__}" + (f" {status}" if status else "")


def run() -> dict:
    dsn = runtime.require_active()
    db.reset(dsn)
    dataset = synthetic.build("empty", seed=3)
    seed.write(dataset)
    user = dataset.users[0]
    candidate_id = email_lab.store_candidate(user, email_lab.fixture("bac_purchase_crc"))
    message = email_lab.fixture("bac_purchase_crc")

    import requests

    results = {}
    with chaos.db_unavailable():
        results["review_with_database_down"] = _outcome(lambda: email_lab.review(user, candidate_id, "accept"))
    with chaos.parser_failure():
        results["parse_with_parser_failure"] = _outcome(lambda: email_lab.parse(message))
    with chaos.backend_500():
        results["http_500"] = _outcome(lambda: requests.get("http://127.0.0.1:9/labs").raise_for_status())
    with chaos.malformed_response():
        results["malformed_json"] = _outcome(lambda: requests.get("http://127.0.0.1:9/labs").json())
    with chaos.timeout():
        results["timeout"] = _outcome(lambda: requests.get("http://127.0.0.1:9/labs"))
    with chaos.billing_verification_failure():
        from backend.product_ops import store_verification

        results["store_verification"] = _outcome(lambda: store_verification.verify_google_purchase("labs", "labs"))
    results["real_network_blocked"] = _outcome(lambda: requests.get("https://example.com", timeout=2))
    results["review_after_recovery"] = _outcome(lambda: email_lab.review(user, candidate_id, "accept")["status"])
    return results
