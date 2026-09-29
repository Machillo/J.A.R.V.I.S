"""Labs database end to end on a real local PostgreSQL (embedded pgserver).

Each test runs in a scrubbed Labs child process, like `python -m labs`.
CI sets DINCR_REQUIRE_PG_TESTS=1 so these fail instead of skipping.
"""
from __future__ import annotations

import uuid

import pytest  # noqa: F401

from labs import db
from labs.tests.helpers import run_child


SEED = """
    import json, sys
    from labs import runtime, db, seed, synthetic
    dsn = runtime.activate()
    db.reset(dsn)
    result = seed.write(synthetic.build(sys.argv[1] if len(sys.argv) > 1 else "{scenario}", 7, heavy_count=300))
    conn = db.connect_labs()
    with conn.cursor() as cur:
        cur.execute("SELECT md5(string_agg(concat_ws(',', t.id, t.transaction_date, t.description, t.amount, t.category, t.workspace_id), '|' ORDER BY t.id)) AS h FROM transactions t")
        result["checksum"] = cur.fetchone()["h"]
    conn.close()
    print(json.dumps(result, default=str))
"""


def test_reset_builds_a_marked_labs_database(labs_dsn):
    result = run_child("""
        import json
        from labs import runtime, db
        dsn = runtime.activate()
        db.reset(dsn)
        conn = db.connect_labs()
        print(json.dumps({"marker": db.has_marker(conn)}))
    """, labs_dsn)
    assert result == {"marker": True}


def test_reset_refuses_a_database_labs_did_not_create(admin_uri):
    import psycopg2

    dsn = db.ensure_database(admin_uri, f"dincr_labs_foreign{uuid.uuid4().hex[:8]}")
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("CREATE TABLE precious(id int); INSERT INTO precious VALUES (1)")
    conn.close()
    code = """
        import json, sys
        from labs import runtime, guard
        try:
            runtime.activate(); out = {"activate": "done"}
        except guard.LabsRefused:
            out = {"activate": "refused"}
        out["backend_loaded"] = any(m.startswith("backend") for m in sys.modules)
        print(json.dumps(out))
    """
    # A local URL leading to a database with tables and no marker (e.g. a tunnel to production).
    assert run_child(code, dsn) == {"activate": "refused", "backend_loaded": False}
    conn = psycopg2.connect(dsn)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM precious")
        assert cur.fetchone()[0] == 1  # untouched
    conn.close()


def test_seed_is_deterministic(labs_dsn):
    first = run_child(SEED.replace("{scenario}", "normal"), labs_dsn)
    second = run_child(SEED.replace("{scenario}", "normal"), labs_dsn)
    assert first["rows"] == second["rows"] and first["checksum"] == second["checksum"]
    assert first["users"] == 5 and first["rows"]["transactions"] > 0


def test_edge_values_are_stored_exactly_and_broken_rows_are_refused(labs_dsn):
    edge = run_child(SEED.replace("{scenario}", "edge"), labs_dsn)
    assert edge["invalid_accepted"] == []
    stored = run_child("""
        import json
        from labs import runtime, db
        runtime.activate()
        conn = db.connect_labs()
        with conn.cursor() as cur:
            cur.execute("SELECT description, amount::text AS a FROM transactions ORDER BY id")
            tx = {r["description"]: r["a"] for r in cur.fetchall()}
            cur.execute("SELECT max(amount)::text AS a FROM expenses"); expense = cur.fetchone()["a"]
            cur.execute("SELECT max(exchange_rate)::text AS r FROM exchange_rates"); rate = cur.fetchone()["r"]
            cur.execute("SELECT max(current_balance)::text AS b FROM account_balances"); balance = cur.fetchone()["b"]
        print(json.dumps({"tx": tx, "expense": expense, "rate": rate, "balance": balance}))
    """, labs_dsn)
    assert stored["tx"]["MAXIMO TRANSACCION"] == "9999999999.99"
    assert stored["tx"]["MONTO MINIMO"] == "0.01" and stored["tx"]["FIN DE AÑO"] == "0.00"
    assert stored["expense"] == "999999999999.99"
    assert stored["rate"] == "99999999.999999"
    assert stored["balance"] == "9999999999999999.99"
    broken = run_child(SEED.replace("{scenario}", "broken"), labs_dsn)
    assert broken["invalid_accepted"] == [] and len(broken["invalid_rejected"]) >= 5


def test_account_isolation_between_synthetic_users(labs_dsn):
    result = run_child("""
        import json
        from labs import runtime, db, seed, synthetic, email_lab
        dsn = runtime.activate()
        db.reset(dsn)
        data = synthetic.build("normal", 7)
        seed.write(data)
        a, b = data.users[0], data.users[1]
        candidate = email_lab.store_candidate(a, email_lab.fixture("bac_purchase_crc"))
        out = {}
        try:
            email_lab.review(b, candidate, "accept"); out["cross"] = "accepted"
        except Exception as exc:
            out["cross"] = getattr(exc, "status_code", type(exc).__name__)
        out["own"] = email_lab.review(a, candidate, "accept")["status"]
        conn = db.connect_labs()
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) AS n FROM transactions WHERE workspace_id=%s AND source IS DISTINCT FROM 'labs'", (b.workspace_id,))
            out["b_mail_rows"] = cur.fetchone()["n"]
        print(json.dumps(out))
    """, labs_dsn)
    assert result == {"cross": 404, "own": "confirmed", "b_mail_rows": 0}


def test_fake_auth_accepts_only_synthetic_users(labs_dsn):
    result = run_child("""
        import json
        from labs import runtime, email_lab
        runtime.activate()
        out = {}
        for name, ident in {"owner": {"role": "owner", "email": "x@labs.invalid"},
                            "real_email": {"role": "user", "email": "person@gmail.com"}}.items():
            try:
                with email_lab.acting_as(ident): out[name] = "accepted"
            except PermissionError:
                out[name] = "refused"
        print(json.dumps(out))
    """, labs_dsn)
    assert result == {"owner": "refused", "real_email": "refused"}


def test_experiment_001_parser_to_transaction(labs_dsn):
    result = run_child("""
        import json
        from labs import runtime
        runtime.activate()
        from labs.experiments import exp001_parser_fixture
        print(json.dumps(exp001_parser_fixture.run(), default=str))
    """, labs_dsn)
    assert result["usd_without_rate"] == "refused: 422"
    assert (result["accepted_crc"], result["accepted_usd"], result["rejected"]) == ("confirmed", "confirmed", "rejected")
    assert result["transactions"] == [
        {"amount": "15000.00", "original_amount": None, "original_currency": None, "exchange_rate": None},
        {"amount": "10605.00", "original_amount": "21.00", "original_currency": "USD", "exchange_rate": "505.000000"},
    ]  # never the parser's matching-only 10395
    assert result["duplicate_detected_by_dedupe_key"] is True


def test_experiment_003_failure_simulation(labs_dsn):
    result = run_child("""
        import json
        from labs import runtime
        runtime.activate()
        from labs.experiments import exp003_failure
        print(json.dumps(exp003_failure.run(), default=str))
    """, labs_dsn)
    assert result == {
        "review_with_database_down": "OperationalError",
        "parse_with_parser_failure": "ValueError",
        "http_500": "HTTPError",
        "malformed_json": "JSONDecodeError",
        "timeout": "Timeout",
        "store_verification": "HTTPException 502",
        "real_network_blocked": "ConnectionError",
        "review_after_recovery": "ok: 'confirmed'",
    }


def test_removing_the_marker_check_would_destroy_a_foreign_database(admin_uri):
    """Mutation: with the marker check forced true, activation and reset wipe a foreign database. The check is load-bearing."""
    import psycopg2

    dsn = db.ensure_database(admin_uri, f"dincr_labs_mut{uuid.uuid4().hex[:8]}")
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    with conn.cursor() as cur:
        cur.execute("CREATE TABLE precious(id int)")
    conn.close()
    result = run_child("""
        import json
        from labs import runtime, db
        db.has_marker = lambda conn: True  # the mutation
        dsn = runtime.activate()
        db.reset(dsn)
        print(json.dumps({"reset": "done"}))
    """, dsn)
    assert result == {"reset": "done"}  # so test_reset_refuses_a_database_labs_did_not_create is what protects it


def test_reset_and_connections_check_the_marker_themselves(labs_dsn):
    """Activation passed on an empty database; objects appear later without the marker: every operation refuses."""
    result = run_child("""
        import json, psycopg2
        from labs import runtime, db, guard
        dsn = runtime.activate()
        raw = psycopg2.connect(dsn); raw.autocommit = True
        raw.cursor().execute("CREATE TABLE someone_elses(id int)")
        raw.close()
        out = {}
        for name, call in {"reset": lambda: db.reset(dsn), "connect": lambda: db.connect_labs()}.items():
            try:
                call(); out[name] = "done"
            except guard.LabsRefused:
                out[name] = "refused"
        print(json.dumps(out))
    """, labs_dsn)
    assert result == {"reset": "refused", "connect": "refused"}


def test_a_non_table_object_makes_a_database_non_empty(admin_uri):
    import psycopg2

    dsn = db.ensure_database(admin_uri, f"dincr_labs_fn{uuid.uuid4().hex[:8]}")
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    conn.cursor().execute("CREATE TYPE precious_kind AS ENUM ('a')")
    conn.close()
    result = run_child("""
        import json
        from labs import runtime, guard
        try:
            runtime.activate(); out = {"activate": "done"}
        except guard.LabsRefused:
            out = {"activate": "refused"}
        print(json.dumps(out))
    """, dsn)
    assert result == {"activate": "refused"}
