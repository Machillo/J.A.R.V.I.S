"""Connecting a bank mailbox must never hide, reset or replace existing financial state.

Regression: a VIP user had ~CRC 300,000 "strategic available" and a registered debt
on Home. After connecting her email both disappeared, although nothing was deleted:
  1. the sync discovers bank accounts (balance unknown, stored as 0 and excluded
     from net worth) and the command center switched its liquid money from the
     declared savings to those accounts' balances (0);
  2. one accepted imported deposit capped the declared income, turning the monthly
     margin negative, which removed the debt priority from the roadmap.

All data below is synthetic.
"""
import copy
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from backend.auth.current_user import reset_current_user, set_current_user
from backend.user_product import financial_identity, gmail_service, service, vip_service

ACCOUNT, WORKSPACE = "account-sintetica", "workspace-sintetico"
OTHER_WORKSPACE = "workspace-ajeno"
ALLOWED_USER_ID, LEGACY_USER_ID = 41, 90
TODAY = date.today()


def _debt():
    return {
        "id": 7, "workspace_id": WORKSPACE, "name": "Tarjeta Sintética", "debt_type": "credit_card",
        "total_amount": 600000, "remaining_amount": 500000, "monthly_payment": 50000,
        "interest_rate": 30, "term_months": None, "payment_day": None,
        "next_payment_date": TODAY + timedelta(days=10), "created_at": TODAY,
    }


def _candidate(candidate_id, transaction_type, amount, description):
    return {
        "id": candidate_id, "email_message_id": 500 + candidate_id, "account_id": ACCOUNT,
        "workspace_id": WORKSPACE, "transaction_id": None, "transaction_date": TODAY,
        "description": description, "amount": amount, "currency": "CRC",
        "transaction_type": transaction_type, "category": "Otros", "bank": "bac",
        "status": "pending", "source_type": "gmail", "financial_account_id": None,
        "is_internal_transfer": False, "resolution_reason": None, "related_candidate_id": None,
        "legacy_user_id": LEGACY_USER_ID,
        # account signals used by the discovery step of the sync
        "movement_direction": "in" if transaction_type == "income" else "out",
        "source_account_reference": "CR00000000000000001234", "destination_account_reference": "CR00000000000000001234",
        "source_account_label": "", "movement_kind": "transfer" if transaction_type == "income" else "card_purchase",
    }


class LedgerDB:
    """Tiny in-memory workspace ledger that answers the queries of these flows."""

    def __init__(self):
        self.state = {
            "profiles": {ACCOUNT: {
                "workspace_id": WORKSPACE, "income_type": "fixed", "fixed_monthly_salary": 1000000,
                "hourly_rate": None, "work_days_per_week": None, "hours_per_day": None,
                "pay_frequency": "monthly", "payday_note": None, "essential_monthly_expenses": 400000,
                "liquid_savings": 300000, "emergency_fund_target": 0, "strategy_preference": "balanced",
                "discretionary_monthly_minimum": 0,
            }},
            "debts": [_debt(), {**_debt(), "id": 8, "workspace_id": OTHER_WORKSPACE, "name": "Ajena"}],
            "accounts": [],
            "transactions": [],
            "candidates": {
                1: _candidate(1, "income", 18500, "Depósito SINPE sintético"),
                2: _candidate(2, "expense", 12000, "Compra sintética"),
                3: _candidate(3, "expense", 9000, "Otra compra sintética"),
            },
        }
        self.seen_workspaces = set()

    def connect(self):
        return LedgerConnection(self)


class LedgerConnection:
    def __init__(self, db):
        self.db = db
        self.work = copy.deepcopy(db.state)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def commit(self):
        self.db.state = copy.deepcopy(self.work)

    @staticmethod
    def _result(rows=None, one=None):
        rows = rows if rows is not None else ([] if one is None else [one])
        return SimpleNamespace(fetchone=lambda: one if one is not None else (rows[0] if rows else None), fetchall=lambda: rows)

    def _transactions(self, start, end, kind, sources=None):
        return [t for t in self.work["transactions"] if t["workspace_id"] == WORKSPACE
                and t["transaction_type"] == kind and start <= t["transaction_date"] < end
                and (sources is None or t["source"] in sources)]

    def execute(self, query, params=()):
        q = " ".join(query.split())
        self.db.seen_workspaces.update(p for p in params if isinstance(p, str) and p.startswith("workspace"))
        work = self.work
        if q.startswith("CREATE TABLE") or q.split()[0] in {"SAVEPOINT", "RELEASE", "ROLLBACK"}:
            return self._result()
        if "FROM financial_profiles WHERE account_id=%s AND workspace_id=%s" in q:
            profile = work["profiles"].get(params[0])
            return self._result(one=dict(profile) if profile and profile["workspace_id"] == params[1] else None)
        if q.startswith("SELECT to_regclass(%s) IS NOT NULL AS exists"):
            return self._result(one={"exists": True})
        if "FROM debts WHERE workspace_id=%s" in q:
            debts = [dict(d) for d in work["debts"] if d["workspace_id"] == params[0]]
            if q.startswith("SELECT COUNT(*) AS count"):
                active = [d for d in debts if d["remaining_amount"] > 0]
                return self._result(one={"count": len(active), "balance": sum(d["remaining_amount"] for d in active),
                                         "missing_interest": sum(not d["interest_rate"] for d in active)})
            if "remaining_amount>0" in q:
                debts = [d for d in debts if d["remaining_amount"] > 0]
            return self._result(sorted(debts, key=lambda d: d["id"], reverse="DESC" in q))
        if "FROM financial_goals WHERE workspace_id=%s AND status='active'" in q:
            return self._result(one={"count": 0, "current": 0, "target": 0}) if "COUNT(*)" in q else self._result([])
        if "FROM account_balances WHERE workspace_id=%s AND is_active=TRUE" in q:
            return self._result([dict(a) for a in work["accounts"] if a["workspace_id"] == params[0] and a["is_active"]])
        if q.startswith("SELECT COALESCE((SELECT SUM(amount) FROM salaries"):
            start, end = params[1], params[2]
            total = lambda kind: sum(t["amount"] for t in self._transactions(start, end, kind))
            return self._result(one={"income": total("income"), "expenses": total("expense"), "debt_paid": total("debt_payment")})
        if "to_char(transaction_date::date,'YYYY-MM') AS month" in q:
            sources, since = set(params[1:-1]), params[-1]
            totals = {}
            for t in self._transactions(since, date.max, "income", sources):
                key = t["transaction_date"].strftime("%Y-%m")
                totals[key] = totals.get(key, 0) + t["amount"]
            return self._result([{"month": key, "total": value} for key, value in totals.items()])
        if "FROM finva_recurring_items WHERE workspace_id=%s AND is_active=TRUE" in q or "LEFT(regexp_replace" in q:
            return self._result([])
        if q.startswith("SELECT status,COUNT(*) total FROM finva_email_candidates"):
            counts = {}
            for c in work["candidates"].values():
                if c["workspace_id"] == params[0]:
                    counts[c["status"]] = counts.get(c["status"], 0) + 1
            return self._result([{"status": key, "total": value} for key, value in counts.items()])
        if "COUNT(*) FILTER (WHERE transaction_type='income') AS income_count" in q:
            since = TODAY - timedelta(days=90)
            income = self._transactions(since, date.max, "income")
            expense = self._transactions(since, date.max, "expense")
            return self._result(one={
                "income_count": len(income), "income_total": sum(t["amount"] for t in income),
                "income_months": len({t["transaction_date"].strftime("%Y-%m") for t in income}),
                "expense_count": len(expense), "expense_total": sum(t["amount"] for t in expense),
                "expense_months": len({t["transaction_date"].strftime("%Y-%m") for t in expense}),
            })
        if q.startswith("INSERT INTO account_balances"):
            (user_id, workspace_id, account_id, name, bank, code, country, kind, last4, currency) = params
            existing = next((a for a in work["accounts"] if (a["workspace_id"], a["account_id"], a["institution_code"], a["account_last4"], a["currency"]) == (workspace_id, account_id, code, last4, currency)), None)
            if existing:
                existing["signals_count"] += 1
            else:
                existing = {"id": 300 + len(work["accounts"]), "user_id": user_id, "workspace_id": workspace_id,
                            "account_id": account_id, "account_name": name, "bank_name": bank, "institution_code": code,
                            "account_type": kind, "account_last4": last4, "currency": currency, "current_balance": 0,
                            "source": "finva_email_discovery", "include_in_net_worth": False, "is_active": True,
                            "ownership_status": "pending", "signals_count": 1}
                work["accounts"].append(existing)
            return self._result(one={"id": existing["id"]})
        if q.startswith("UPDATE finva_email_candidates SET financial_account_id"):
            work["candidates"][params[1]]["financial_account_id"] = params[0]
            return self._result()
        if q.startswith("SELECT c.*,g.legacy_user_id"):
            candidate = work["candidates"].get(params[0])
            ok = candidate and (candidate["account_id"], candidate["workspace_id"]) == (params[1], params[2])
            return self._result(one=dict(candidate) if ok else None)
        if q.startswith("INSERT INTO transactions"):
            (tdate, description, amount, kind, category, _account, source, _notes, user_id, workspace_id, _fa) = params
            transaction_id = 9000 + len(work["transactions"])
            work["transactions"].append({"id": transaction_id, "transaction_date": tdate, "description": description,
                                         "amount": amount, "transaction_type": kind, "source": source,
                                         "user_id": user_id, "workspace_id": workspace_id})
            return self._result(one={"id": transaction_id})
        if q.startswith("INSERT INTO financial_input_events") or q.startswith("INSERT INTO notification_jobs"):
            return self._result()
        if q.startswith("UPDATE finva_email_candidates"):
            candidate = work["candidates"][params[-1]]
            candidate["status"] = "rejected" if "status='rejected'" in q else "confirmed"
            if "transaction_id=%s" in q:
                candidate["transaction_id"] = params[0]
            return self._result()
        if q.startswith("UPDATE finva_email_messages"):
            return self._result()
        if q.startswith("SELECT id FROM finva_email_candidates WHERE account_id=%s AND workspace_id=%s AND related_candidate_id=%s"):
            return self._result([])  # no statement/notification copies linked in this scenario
        raise AssertionError(f"Unexpected query: {q[:100]}")


@pytest.fixture
def db(monkeypatch):
    database = LedgerDB()
    for module in (vip_service, service, gmail_service):
        monkeypatch.setattr(module, "get_connection", database.connect)
    monkeypatch.setattr(service, "require_feature", lambda *_args, **_kwargs: None)
    token = set_current_user({"id": ALLOWED_USER_ID, "account_id": ACCOUNT, "workspace_id": WORKSPACE, "role": "user"})
    yield database
    reset_current_user(token)


def _sync_discovers_accounts(db):
    """What the mail sync does for each stored candidate: link a detected account."""
    with db.connect() as conn:
        for candidate_id, candidate in conn.work["candidates"].items():
            financial_identity.discover_candidate_account(
                conn, candidate_id=candidate_id, candidate=candidate,
                account_id=ACCOUNT, workspace_id=WORKSPACE, legacy_user_id=LEGACY_USER_ID,
            )
        conn.commit()


def _home():
    center = vip_service.get_vip_command_center()
    return {
        "available": center["safe_to_spend"]["amount"],
        "margin": center["safe_to_spend"]["monthly_margin"],
        "cash_6m": next(p["cash"] for p in center["projections"] if p["months"] == 6),
        "debt_6m": next(p["debt"] for p in center["projections"] if p["months"] == 6),
        "liabilities": center["net_worth"]["liabilities"],
        "debt_priority": [item["title"] for item in center["roadmap"] if "Tarjeta Sintética" in item["title"]],
        "priority": center["director"]["priority"],
        "recommended_debt": (center["debt_planner"]["recommended"] or {}).get("target"),
    }


def _financial_state():
    situation = service.get_financial_situation()
    return {
        "profile": situation["financial_profile"],
        "debts": situation["debts"],
        "debt_list": service.list_user_debts(),
        "strategy": service.get_strategy_vip(),
    }


def test_connecting_and_reviewing_mail_keeps_home_strategy_and_debts(db):
    before_home, before_state = _home(), _financial_state()
    assert before_home["available"] == 250000  # CRC 300,000 savings - the 50,000 debt payment due in 10 days
    assert before_home["debt_priority"] == ["Abonar a Tarjeta Sintética"]

    _sync_discovers_accounts(db)  # connect + first sync: candidates and detected accounts
    assert db.state["accounts"], "the sync discovered the bank account"
    assert _home() == before_home

    assert gmail_service.review_gmail_candidate(1, "accept")["status"] == "confirmed"  # imported deposit
    assert gmail_service.review_gmail_candidate(2, "accept")["status"] == "confirmed"  # imported purchase
    assert gmail_service.review_gmail_candidate(3, "reject")["status"] == "rejected"
    gmail_service.review_gmail_candidate(1, "accept")  # repeated tap: no second transaction

    after_home, after_state = _home(), _financial_state()
    assert after_home == before_home
    assert after_state["profile"] == before_state["profile"]
    assert after_state["debts"] == before_state["debts"]
    assert after_state["debt_list"] == before_state["debt_list"]
    assert after_state["strategy"] == before_state["strategy"]

    # Nothing was deleted or overwritten, and everything stayed in the same workspace.
    assert db.state["debts"] == LedgerDB().state["debts"]
    assert db.state["profiles"] == LedgerDB().state["profiles"]
    assert len(db.state["transactions"]) == 2
    assert {t["workspace_id"] for t in db.state["transactions"]} == {WORKSPACE}
    assert {a["workspace_id"] for a in db.state["accounts"]} == {WORKSPACE}
    assert db.seen_workspaces == {WORKSPACE}


def test_imported_movements_stay_visible_in_reports(db):
    _sync_discovers_accounts(db)
    gmail_service.review_gmail_candidate(1, "accept")
    gmail_service.review_gmail_candidate(2, "accept")
    current = vip_service.get_vip_command_center()["reports"]["current"]
    assert current["income"] == 18500 and current["expenses"] == 12000


def test_discovered_account_with_unknown_balance_does_not_replace_savings(db):
    _sync_discovers_accounts(db)
    db.state["accounts"][0]["ownership_status"] = "own"  # confirmed as own; balance still unknown
    center = vip_service.get_vip_command_center()
    assert center["safe_to_spend"]["amount"] == 250000
    assert center["projections"][0]["cash"] == 300000 + center["safe_to_spend"]["monthly_margin"]


def test_balance_the_user_entered_still_drives_liquidity(db):
    db.state["accounts"].append({
        "id": 1, "workspace_id": WORKSPACE, "account_id": ACCOUNT, "account_name": "Ahorro", "bank_name": "BAC",
        "currency": "CRC", "current_balance": 80000, "account_type": "savings", "institution_code": "bac", "account_last4": "9999",
        "include_in_net_worth": True, "is_active": True,
    })
    _sync_discovers_accounts(db)
    center = vip_service.get_vip_command_center()
    assert center["net_worth"]["assets"] == 80000
    assert center["safe_to_spend"]["amount"] == 30000  # 80,000 - the 50,000 debt payment due in 10 days


def test_manual_income_still_caps_the_declared_income(db):
    """The conservative rule itself is unchanged for income the user records.

    Pre-existing (not changed here): the in-progress month counts as observed; see
    the follow-up in the PR.
    """
    db.state["transactions"].append({"id": 1, "transaction_date": TODAY, "description": "Ingreso manual",
                                     "amount": 600000, "transaction_type": "income", "source": "finva",
                                     "user_id": LEGACY_USER_ID, "workspace_id": WORKSPACE})
    center = vip_service.get_vip_command_center()
    assert center["variable_income"]["conservative"] == 600000
    assert center["safe_to_spend"]["monthly_margin"] == 150000


def _imported_income(amount, months_ago=0):
    day = TODAY.replace(day=1)
    for _ in range(months_ago):
        day = (day - timedelta(days=1)).replace(day=1)
    return {"id": 100 + months_ago, "transaction_date": day, "description": "Depósito importado", "amount": amount,
            "transaction_type": "income", "source": "finva_gmail", "user_id": LEGACY_USER_ID, "workspace_id": WORKSPACE}


def test_without_declared_income_imports_remain_the_income_evidence(db):
    db.state["profiles"][ACCOUNT].update({"income_type": None, "fixed_monthly_salary": None})
    db.state["transactions"] += [_imported_income(700000, 1), _imported_income(700000, 2)]
    center = vip_service.get_vip_command_center()
    assert center["variable_income"]["conservative"] == 700000
    assert center["variable_income"]["months_observed"] == 2


def test_steady_imported_salary_below_declared_income_does_not_replace_it(db):
    """Documents the rule decision (HUMAN GATE in the PR): imports never silently
    replace the declared income; a lower imported salary is not used as the cap."""
    db.state["transactions"] += [_imported_income(600000, 1), _imported_income(600000, 2), _imported_income(600000, 3)]
    center = vip_service.get_vip_command_center()
    assert center["variable_income"]["conservative"] == 1000000
    assert center["reports"]["previous"]["income"] == 600000


def test_usd_only_account_does_not_zero_the_crc_savings(db):
    db.state["accounts"].append({
        "id": 1, "workspace_id": WORKSPACE, "account_id": ACCOUNT, "account_name": "Dólares", "bank_name": "BAC",
        "currency": "USD", "current_balance": 900, "account_type": "savings", "institution_code": "bac",
        "account_last4": "8888", "include_in_net_worth": True, "is_active": True,
    })
    assert vip_service.get_vip_command_center()["safe_to_spend"]["amount"] == 250000


def test_discovered_accounts_do_not_raise_the_data_quality_score(db):
    before = vip_service.get_vip_command_center()["score"]["value"]
    _sync_discovers_accounts(db)
    assert vip_service.get_vip_command_center()["score"]["value"] == before
