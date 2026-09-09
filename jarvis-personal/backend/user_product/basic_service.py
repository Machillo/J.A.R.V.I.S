from __future__ import annotations

import calendar
import re
from datetime import date, datetime
from typing import Any

from fastapi import HTTPException

from backend.auth.current_user import get_current_account_id, get_current_workspace_id
from backend.core.database import get_connection


def _money(value: Any) -> float:
    return round(float(value or 0), 2)


def _month(value: str | None = None) -> date:
    try:
        return date.fromisoformat(f"{value}-01") if value else date.today().replace(day=1)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="El periodo debe tener formato YYYY-MM.") from exc


def _next_month(start: date) -> date:
    return date(start.year + (start.month == 12), 1 if start.month == 12 else start.month + 1, 1)


def _shift_month(start: date, delta: int) -> date:
    index = start.year * 12 + start.month - 1 + delta
    return date(index // 12, index % 12 + 1, 1)


def _profile(conn, account_id: str, workspace_id: str) -> dict:
    row = conn.execute(
        """SELECT income_type,fixed_monthly_salary,hourly_rate,work_days_per_week,hours_per_day,
                  pay_frequency,payday_note,essential_monthly_expenses,liquid_savings
           FROM financial_profiles WHERE account_id=%s AND workspace_id=%s""",
        (account_id, workspace_id),
    ).fetchone()
    return dict(row) if row else {}


def _estimated_income(profile: dict) -> float:
    if profile.get("income_type") == "fixed":
        return _money(profile.get("fixed_monthly_salary"))
    return round(_money(profile.get("hourly_rate")) * _money(profile.get("hours_per_day")) * _money(profile.get("work_days_per_week")) * 52 / 12, 2)


def _ledger_totals(conn, workspace_id: str, start: date, end: date) -> dict:
    row = conn.execute(
        """SELECT
          COALESCE((SELECT SUM(amount) FROM salaries WHERE workspace_id=%s AND created_at >= %s AND created_at < %s),0)
          + COALESCE((SELECT SUM(amount) FROM payroll_events WHERE workspace_id=%s AND amount>0 AND created_at >= %s AND created_at < %s),0)
          + COALESCE((SELECT SUM(amount) FROM transactions WHERE workspace_id=%s AND transaction_type='income' AND transaction_date::date >= %s AND transaction_date::date < %s),0) AS income,
          COALESCE((SELECT SUM(amount) FROM expenses WHERE workspace_id=%s AND created_at >= %s AND created_at < %s),0)
          + COALESCE((SELECT SUM(amount) FROM transactions WHERE workspace_id=%s AND transaction_type='expense' AND transaction_date::date >= %s AND transaction_date::date < %s),0) AS expenses,
          COALESCE((SELECT SUM(amount) FROM transactions WHERE workspace_id=%s AND transaction_type='debt_payment' AND transaction_date::date >= %s AND transaction_date::date < %s),0) AS debt_paid""",
        (workspace_id,start,end, workspace_id,start,end, workspace_id,start,end,
         workspace_id,start,end, workspace_id,start,end, workspace_id,start,end),
    ).fetchone()
    return {key: _money(row[key]) for key in ("income", "expenses", "debt_paid")}


def _monthly_equivalent(amount: float, frequency: str) -> float:
    return round(amount * {"weekly": 52/12, "biweekly": 26/12, "monthly": 1, "quarterly": 1/3, "annual": 1/12}.get(frequency, 1), 2)


def get_basic_dashboard() -> dict:
    account_id, workspace_id = get_current_account_id(), get_current_workspace_id()
    current = date.today().replace(day=1)
    with get_connection() as conn:
        profile = _profile(conn, account_id, workspace_id)
        months = []
        for offset in range(-5, 1):
            start = _shift_month(current, offset)
            values = _ledger_totals(conn, workspace_id, start, _next_month(start))
            months.append({"month": start.strftime("%Y-%m"), **values, "balance": round(values["income"]-values["expenses"]-values["debt_paid"],2)})
        categories = conn.execute(
            """SELECT category,ROUND(SUM(amount),2) AS amount FROM (
                 SELECT category,amount FROM expenses WHERE workspace_id=%s AND created_at >= %s AND created_at < %s
                 UNION ALL SELECT category,amount FROM transactions WHERE workspace_id=%s AND transaction_type='expense' AND transaction_date::date >= %s AND transaction_date::date < %s
               ) x GROUP BY category ORDER BY amount DESC""",
            (workspace_id,current,_next_month(current),workspace_id,current,_next_month(current)),
        ).fetchall()
        debts = conn.execute("SELECT COALESCE(SUM(total_amount),0) original,COALESCE(SUM(remaining_amount),0) remaining,COALESCE(SUM(monthly_payment),0) monthly FROM debts WHERE workspace_id=%s",(workspace_id,)).fetchone()
        goals = conn.execute("SELECT COALESCE(SUM(target_amount),0) target,COALESCE(SUM(current_amount),0) current,COUNT(*) FILTER(WHERE status='active') active FROM financial_goals WHERE workspace_id=%s",(workspace_id,)).fetchone()
    now, previous = months[-1], months[-2]
    debt_original, debt_remaining = _money(debts["original"]), _money(debts["remaining"])
    goal_target, goal_current = _money(goals["target"]), _money(goals["current"])
    income = now["income"] or _estimated_income(profile)
    return {
        "month": current.strftime("%Y-%m"), "income": income, "recorded_income": now["income"],
        "expenses": now["expenses"], "debt_paid": now["debt_paid"], "balance": round(income-now["expenses"]-now["debt_paid"],2),
        "debt": {"original": debt_original,"remaining": debt_remaining,"monthly":_money(debts["monthly"]),"progress":round((1-debt_remaining/debt_original)*100,1) if debt_original else 0},
        "savings": _money(profile.get("liquid_savings")),
        "goals": {"target":goal_target,"current":goal_current,"active":int(goals["active"] or 0),"progress":round(goal_current/goal_target*100,1) if goal_target else 0},
        "categories":[dict(row) for row in categories], "monthly_history":months,
        "trends":{"income":round(now["income"]-previous["income"],2),"expenses":round(now["expenses"]-previous["expenses"],2),"balance":round(now["balance"]-previous["balance"],2)},
    }


def get_guided_budget() -> dict:
    account_id, workspace_id = get_current_account_id(), get_current_workspace_id()
    current = date.today().replace(day=1)
    with get_connection() as conn:
        profile = _profile(conn, account_id, workspace_id)
        income = _estimated_income(profile)
        debts = _money(conn.execute("SELECT COALESCE(SUM(monthly_payment),0) total FROM debts WHERE workspace_id=%s AND remaining_amount>0",(workspace_id,)).fetchone()["total"])
        recurring_rows = conn.execute("SELECT amount,frequency,item_type FROM finva_recurring_items WHERE workspace_id=%s AND is_active=TRUE",(workspace_id,)).fetchall()
        recurring_expenses = round(sum(_monthly_equivalent(_money(r["amount"]),r["frequency"]) for r in recurring_rows if r["item_type"]=="expense"),2)
        recurring_income = round(sum(_monthly_equivalent(_money(r["amount"]),r["frequency"]) for r in recurring_rows if r["item_type"]=="income"),2)
        items = conn.execute("SELECT category,monthly_limit,is_system FROM finva_budget_items WHERE workspace_id=%s ORDER BY is_system DESC,category",(workspace_id,)).fetchall()
        actual = conn.execute("""SELECT category,ROUND(SUM(amount),2) amount FROM (
            SELECT category,amount FROM expenses WHERE workspace_id=%s AND created_at >= %s AND created_at < %s
            UNION ALL SELECT category,amount FROM transactions WHERE workspace_id=%s AND transaction_type='expense' AND transaction_date::date >= %s AND transaction_date::date < %s
        ) q GROUP BY category""",(workspace_id,current,_next_month(current),workspace_id,current,_next_month(current))).fetchall()
    income += recurring_income
    fixed = debts + recurring_expenses
    distributable = max(income-fixed,0)
    proposed = [
        {"category":"Comida","monthly_limit":round(distributable*.45,2)},
        {"category":"Transporte","monthly_limit":round(distributable*.20,2)},
        {"category":"Personal","monthly_limit":round(distributable*.15,2)},
        {"category":"Ahorro y metas","monthly_limit":round(distributable*.15,2)},
        {"category":"Otros","monthly_limit":round(distributable*.05,2)},
    ]
    chosen = [dict(row) for row in items] or proposed
    spent = {row["category"]:_money(row["amount"]) for row in actual}
    return {"income":income,"debt_minimums":debts,"recurring_expenses":recurring_expenses,"available_for_categories":round(distributable,2),"is_proposal":not bool(items),"items":[{**row,"spent":spent.get(row["category"],0),"remaining":round(_money(row["monthly_limit"])-spent.get(row["category"],0),2)} for row in chosen],"total_budgeted":round(sum(_money(row["monthly_limit"]) for row in chosen),2)}


def save_guided_budget(payload) -> dict:
    account_id, workspace_id = get_current_account_id(), get_current_workspace_id()
    seen = set()
    with get_connection() as conn:
        conn.execute("DELETE FROM finva_budget_items WHERE workspace_id=%s", (workspace_id,))
        for item in payload.items:
            category = item.category.strip()
            if not category or category.lower() in seen:
                raise HTTPException(status_code=422, detail="Las categorías deben ser únicas y tener nombre.")
            seen.add(category.lower())
            conn.execute("""INSERT INTO finva_budget_items(account_id,workspace_id,category,monthly_limit,updated_at)
                VALUES(%s,%s,%s,%s,NOW())""",(account_id,workspace_id,category,item.monthly_limit))
        conn.commit()
    return get_guided_budget()


def list_recurring_items() -> dict:
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        rows=conn.execute("SELECT id,name,amount,category,item_type,frequency,due_day,is_active,created_at FROM finva_recurring_items WHERE workspace_id=%s ORDER BY is_active DESC,due_day NULLS LAST,id DESC",(workspace_id,)).fetchall()
    items=[]
    for row in rows:
        item=dict(row); item["monthly_amount"]=_monthly_equivalent(_money(item["amount"]),item["frequency"]); item["annual_amount"]=round(item["monthly_amount"]*12,2); items.append(item)
    return {"items":items,"monthly_expenses":round(sum(i["monthly_amount"] for i in items if i["is_active"] and i["item_type"]=="expense"),2),"annual_expenses":round(sum(i["annual_amount"] for i in items if i["is_active"] and i["item_type"]=="expense"),2)}


def create_recurring_item(payload) -> dict:
    account_id,workspace_id=get_current_account_id(),get_current_workspace_id()
    with get_connection() as conn:
        row=conn.execute("""INSERT INTO finva_recurring_items(account_id,workspace_id,name,amount,category,item_type,frequency,due_day,is_active)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id,name,amount,category,item_type,frequency,due_day,is_active""",(account_id,workspace_id,payload.name.strip(),payload.amount,payload.category.strip() or "general",payload.item_type,payload.frequency,payload.due_day,payload.is_active)).fetchone();conn.commit()
    return row


def update_recurring_item(item_id:int,payload) -> dict:
    workspace_id=get_current_workspace_id()
    with get_connection() as conn:
        row=conn.execute("""UPDATE finva_recurring_items SET name=%s,amount=%s,category=%s,item_type=%s,frequency=%s,due_day=%s,is_active=%s,updated_at=NOW()
          WHERE id=%s AND workspace_id=%s RETURNING id,name,amount,category,item_type,frequency,due_day,is_active""",(payload.name.strip(),payload.amount,payload.category.strip() or "general",payload.item_type,payload.frequency,payload.due_day,payload.is_active,item_id,workspace_id)).fetchone()
        if not row: raise HTTPException(status_code=404,detail="Recurrente no encontrado.")
        conn.commit()
    return row


def delete_recurring_item(item_id:int) -> dict:
    workspace_id=get_current_workspace_id()
    with get_connection() as conn:
        row=conn.execute("DELETE FROM finva_recurring_items WHERE id=%s AND workspace_id=%s RETURNING id",(item_id,workspace_id)).fetchone()
        if not row: raise HTTPException(status_code=404,detail="Recurrente no encontrado.")
        conn.commit()
    return {"status":"ok","id":item_id}


def get_financial_calendar(period: str | None = None) -> dict:
    account_id,workspace_id=get_current_account_id(),get_current_workspace_id(); start=_month(period); end=_next_month(start); events=[]
    with get_connection() as conn:
        profile=_profile(conn,account_id,workspace_id)
        recurring=conn.execute("SELECT id,name,amount,item_type,due_day FROM finva_recurring_items WHERE workspace_id=%s AND is_active=TRUE AND due_day IS NOT NULL",(workspace_id,)).fetchall()
        debts=conn.execute("SELECT id,name,monthly_payment,payment_day,next_payment_date FROM debts WHERE workspace_id=%s AND remaining_amount>0",(workspace_id,)).fetchall()
        goals=conn.execute("SELECT id,name,target_amount,current_amount,target_date FROM financial_goals WHERE workspace_id=%s AND status='active' AND target_date IS NOT NULL",(workspace_id,)).fetchall()
    last=calendar.monthrange(start.year,start.month)[1]
    for item in recurring:
        day=min(int(item["due_day"]),last); events.append({"date":date(start.year,start.month,day).isoformat(),"kind":item["item_type"],"name":item["name"],"amount":_money(item["amount"]),"source":"recurring","source_id":item["id"]})
    for debt in debts:
        candidate=None
        if debt.get("next_payment_date"):
            parsed=debt["next_payment_date"] if isinstance(debt["next_payment_date"],date) else date.fromisoformat(str(debt["next_payment_date"])[:10])
            if start<=parsed<end:candidate=parsed
        if not candidate and debt.get("payment_day"):candidate=date(start.year,start.month,min(int(debt["payment_day"]),last))
        if candidate:events.append({"date":candidate.isoformat(),"kind":"debt","name":debt["name"],"amount":_money(debt["monthly_payment"]),"source":"debt","source_id":debt["id"]})
    for goal in goals:
        try:
            parsed=date.fromisoformat(str(goal["target_date"])[:10])
        except (TypeError, ValueError):
            continue
        if start<=parsed<end:events.append({"date":parsed.isoformat(),"kind":"goal","name":goal["name"],"amount":round(max(_money(goal["target_amount"])-_money(goal["current_amount"]),0),2),"source":"goal","source_id":goal["id"]})
    pay_days=[int(x) for x in re.findall(r"\b(?:[1-9]|[12]\d|3[01])\b",str(profile.get("payday_note") or ""))]
    for day in sorted(set(pay_days)):
        events.append({"date":date(start.year,start.month,min(day,last)).isoformat(),"kind":"income","name":"Ingreso esperado","amount":0,"source":"profile"})
    events.sort(key=lambda item:(item["date"],0 if item["kind"]=="income" else 1,item["name"]))
    return {"period":start.strftime("%Y-%m"),"events":events,"summary":{"income_events":sum(e["kind"]=="income" for e in events),"payments":round(sum(e["amount"] for e in events if e["kind"] in {"expense","debt"}),2),"commitments":sum(e["kind"] in {"expense","debt"} for e in events)}}


def get_basic_report(period: str | None = None) -> dict:
    account_id,workspace_id=get_current_account_id(),get_current_workspace_id();start=_month(period);previous=_shift_month(start,-1)
    with get_connection() as conn:
        current=_ledger_totals(conn,workspace_id,start,_next_month(start)); prior=_ledger_totals(conn,workspace_id,previous,start)
        categories=conn.execute("""SELECT category,ROUND(SUM(amount),2) amount FROM (
          SELECT category,amount FROM expenses WHERE workspace_id=%s AND created_at >= %s AND created_at < %s
          UNION ALL SELECT category,amount FROM transactions WHERE workspace_id=%s AND transaction_type='expense' AND transaction_date::date >= %s AND transaction_date::date < %s) q GROUP BY category ORDER BY amount DESC""",(workspace_id,start,_next_month(start),workspace_id,start,_next_month(start))).fetchall()
        contributions=_money(conn.execute("SELECT COALESCE(SUM(amount),0) total FROM finva_goal_contributions WHERE workspace_id=%s AND contribution_date >= %s AND contribution_date < %s",(workspace_id,start,_next_month(start))).fetchone()["total"])
        debt=conn.execute("SELECT COALESCE(SUM(total_amount),0) original,COALESCE(SUM(remaining_amount),0) remaining FROM debts WHERE workspace_id=%s",(workspace_id,)).fetchone()
        goals=conn.execute("SELECT COALESCE(SUM(target_amount),0) target,COALESCE(SUM(current_amount),0) current FROM financial_goals WHERE workspace_id=%s",(workspace_id,)).fetchone()
        profile=_profile(conn,account_id,workspace_id)
    income=current["income"] or _estimated_income(profile); balance=round(income-current["expenses"]-current["debt_paid"]-contributions,2)
    return {"period":start.strftime("%Y-%m"),"income":income,"expenses":current["expenses"],"debt_paid":current["debt_paid"],"goal_contributions":contributions,"saved":max(balance,0),"balance":balance,"categories":[dict(r) for r in categories],"comparison":{"income":round(current["income"]-prior["income"],2),"expenses":round(current["expenses"]-prior["expenses"],2),"debt_paid":round(current["debt_paid"]-prior["debt_paid"],2)},"debt":{"remaining":_money(debt["remaining"]),"progress":round((1-_money(debt["remaining"])/_money(debt["original"]))*100,1) if _money(debt["original"]) else 0},"goals":{"current":_money(goals["current"]),"target":_money(goals["target"]),"progress":round(_money(goals["current"])/_money(goals["target"])*100,1) if _money(goals["target"]) else 0}}
