"""EXPERIMENT 001: synthetic bank email -> parser -> candidate -> Accept/Reject -> transaction.

Uses DINCR's real parser and real review command on the Labs database, as a
synthetic user. Shows the USD rule: the parser's matching-only amount (default
rate) never becomes the saved amount; the user's rate does.
"""
from __future__ import annotations

from decimal import Decimal

from labs import db, email_lab, runtime, seed, synthetic


def run() -> dict:
    dsn = runtime.require_active()
    db.reset(dsn)
    dataset = synthetic.build("empty", seed=1)
    seed.write(dataset)
    user = dataset.users[0]
    fixtures = email_lab.load_fixtures()
    parsed = {case["name"]: email_lab.report({**case, "received_at": fixtures["received_at"]}) for case in fixtures["cases"]}

    crc_id = email_lab.store_candidate(user, email_lab.fixture("bac_purchase_crc"))
    usd_id = email_lab.store_candidate(user, email_lab.fixture("bac_purchase_usd"))
    reject_id = email_lab.store_candidate(user, email_lab.fixture("bac_strange_merchant"))

    accepted_crc = email_lab.review(user, crc_id, "accept")
    try:
        email_lab.review(user, usd_id, "accept")
        usd_without_rate = "accepted (unexpected)"
    except Exception as exc:  # DINCR asks the user for a rate: 422
        usd_without_rate = f"refused: {getattr(exc, 'status_code', type(exc).__name__)}"
    accepted_usd = email_lab.review(user, usd_id, "accept", {"amount": 21, "exchange_rate": 505})
    rejected = email_lab.review(user, reject_id, "reject")

    conn = db.connect_labs()
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT amount, original_amount, original_currency, exchange_rate FROM transactions
                           WHERE workspace_id=%s ORDER BY id""", (user.workspace_id,))
            transactions = [{k: (str(v) if isinstance(v, Decimal) else v) for k, v in row.items()} for row in cur.fetchall()]
    finally:
        conn.close()
    duplicate = parsed["bac_duplicate"]["dedupe_key"] == parsed["bac_purchase_crc"]["dedupe_key"]
    return {"parsed": parsed, "usd_without_rate": usd_without_rate,
            "accepted_crc": accepted_crc.get("status"), "accepted_usd": accepted_usd.get("status"),
            "rejected": rejected.get("status"), "transactions": transactions, "duplicate_detected_by_dedupe_key": duplicate}
