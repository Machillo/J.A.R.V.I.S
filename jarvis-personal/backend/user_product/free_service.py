from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import HTTPException

from backend.auth.current_user import get_current_account_id, get_current_workspace_id
from backend.core.database import get_connection
from backend.finance.category_catalog import expense_type_for_category, normalize_category


def _money(value: Any) -> float:
    return round(float(value or 0), 2)


def _transaction_date_sql() -> str:
    raw = "NULLIF(BTRIM(transaction_date::text),'')"
    return f"CASE WHEN {raw} ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}' THEN SUBSTRING({raw} FROM 1 FOR 10)::date ELSE NULL END"


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


def _period_totals(conn, workspace_id: str, start: date, end: date) -> dict:
    transaction_date = _transaction_date_sql()
    row = conn.execute(
        f"""SELECT
          COALESCE((SELECT SUM(amount) FROM salaries WHERE workspace_id=%s AND created_at::date >= %s AND created_at::date < %s),0)
          + COALESCE((SELECT SUM(amount) FROM payroll_events WHERE workspace_id=%s AND amount>0 AND created_at::date >= %s AND created_at::date < %s),0)
          + COALESCE((SELECT SUM(amount) FROM transactions WHERE workspace_id=%s AND transaction_type='income' AND {transaction_date} >= %s AND {transaction_date} < %s),0) AS income,
          COALESCE((SELECT SUM(amount) FROM expenses WHERE workspace_id=%s AND created_at::date >= %s AND created_at::date < %s),0)
          + COALESCE((SELECT SUM(amount) FROM transactions WHERE workspace_id=%s AND transaction_type='expense' AND {transaction_date} >= %s AND {transaction_date} < %s),0) AS expenses,
          COALESCE((SELECT SUM(amount) FROM transactions WHERE workspace_id=%s AND transaction_type='debt_payment' AND {transaction_date} >= %s AND {transaction_date} < %s),0) AS debt_paid""",
        (workspace_id,start,end, workspace_id,start,end, workspace_id,start,end,
         workspace_id,start,end, workspace_id,start,end, workspace_id,start,end),
    ).fetchone()
    return {key: _money(row[key]) for key in ("income", "expenses", "debt_paid")}


def _categories(conn, workspace_id: str, start: date, end: date) -> list[dict]:
    transaction_date = _transaction_date_sql()
    rows = conn.execute(
        f"""SELECT COALESCE(NULLIF(BTRIM(category),''),'Sin categoría') category,ROUND(SUM(amount),2) amount
           FROM (
             SELECT category,amount FROM expenses WHERE workspace_id=%s AND created_at::date >= %s AND created_at::date < %s
             UNION ALL
             SELECT category,amount FROM transactions WHERE workspace_id=%s AND transaction_type='expense'
               AND {transaction_date} >= %s AND {transaction_date} < %s
           ) q GROUP BY category ORDER BY amount DESC""",
        (workspace_id,start,end,workspace_id,start,end),
    ).fetchall()
    return [{"category": row["category"], "amount": _money(row["amount"])} for row in rows]


def get_free_dashboard() -> dict:
    workspace_id = get_current_workspace_id()
    current = date.today().replace(day=1)
    with get_connection() as conn:
        history = []
        for offset in range(-5, 1):
            start = _shift_month(current, offset)
            totals = _period_totals(conn, workspace_id, start, _next_month(start))
            history.append({"month": start.strftime("%Y-%m"), **totals, "balance": round(totals["income"]-totals["expenses"]-totals["debt_paid"],2)})
        categories = _categories(conn, workspace_id, current, _next_month(current))
        debt = conn.execute("SELECT COALESCE(SUM(remaining_amount),0) balance FROM debts WHERE workspace_id=%s", (workspace_id,)).fetchone()
    now = history[-1]
    return {
        "month": current.strftime("%Y-%m"), "income": now["income"], "expenses": now["expenses"],
        "debt_paid": now["debt_paid"], "debt_balance": _money(debt["balance"]),
        "balance": now["balance"], "available_after_commitments": now["balance"],
        "categories": categories, "monthly_history": history,
    }


def get_free_monthly_summary(period: str | None = None) -> dict:
    account_id, workspace_id = get_current_account_id(), get_current_workspace_id()
    start = _month(period)
    with get_connection() as conn:
        totals = _period_totals(conn, workspace_id, start, _next_month(start))
        categories = _categories(conn, workspace_id, start, _next_month(start))
        goals = conn.execute(
            "SELECT COALESCE(SUM(current_amount),0) current,COALESCE(SUM(target_amount),0) target FROM financial_goals WHERE workspace_id=%s",
            (workspace_id,),
        ).fetchone()
        profile = conn.execute("SELECT liquid_savings FROM financial_profiles WHERE account_id=%s AND workspace_id=%s", (account_id,workspace_id)).fetchone()
    balance = round(totals["income"]-totals["expenses"]-totals["debt_paid"],2)
    target, current = _money(goals["target"]), _money(goals["current"])
    return {
        "period": start.strftime("%Y-%m"), **totals, "balance": balance,
        "top_category": categories[0] if categories else None, "categories": categories,
        "savings": _money(profile["liquid_savings"] if profile else 0),
        "goals": {"current":current,"target":target,"progress":round(current/target*100,1) if target else 0},
    }


def list_free_movements() -> list[dict]:
    workspace_id = get_current_workspace_id()
    transaction_date = _transaction_date_sql()
    with get_connection() as conn:
        rows = conn.execute(
            f"""SELECT * FROM (
              SELECT 'salary:'||id movement_id,id source_id,'salary' origin,created_at::date transaction_date,
                     source description,amount,'income' transaction_type,COALESCE(category,'Salario') category,'' notes,TRUE editable
              FROM salaries WHERE workspace_id=%s
              UNION ALL
              SELECT 'expense:'||id,id,'expense',created_at::date,COALESCE(description,''),amount,'expense',category,'',TRUE
              FROM expenses WHERE workspace_id=%s
              UNION ALL
              SELECT 'payroll:'||id,id,'payroll',created_at::date,COALESCE(description,'Horas extra'),amount,'income','Horas extra','',TRUE
              FROM payroll_events WHERE workspace_id=%s AND amount>0
              UNION ALL
              SELECT 'transaction:'||id,id,'transaction',{transaction_date},description,amount,
                     CASE WHEN transaction_type='income' THEN 'income' ELSE 'expense' END,category,COALESCE(notes,''),
                     (source IN ('finva','manual','manual_expense'))
              FROM transactions WHERE workspace_id=%s
            ) movements ORDER BY transaction_date DESC,source_id DESC""",
            (workspace_id,workspace_id,workspace_id,workspace_id),
        ).fetchall()
    return [dict(row) for row in rows]


def update_free_movement(movement_id: str, payload) -> dict:
    workspace_id = get_current_workspace_id()
    try:
        origin, raw_id = movement_id.split(":", 1)
        source_id = int(raw_id)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Identificador de movimiento inválido.") from exc
    with get_connection() as conn:
        if origin == "salary":
            if payload.transaction_type != "income": raise HTTPException(status_code=422,detail="Un ingreso debe conservar su tipo.")
            row=conn.execute("""UPDATE salaries SET amount=%s,source=%s,category=%s,created_at=%s::date+TIME '12:00'
                WHERE id=%s AND workspace_id=%s RETURNING id""",(payload.amount,payload.description.strip(),payload.category.strip(),payload.transaction_date,source_id,workspace_id)).fetchone()
        elif origin == "expense":
            if payload.transaction_type != "expense": raise HTTPException(status_code=422,detail="Un gasto debe conservar su tipo.")
            category=payload.category.strip() or "Compras"
            row=conn.execute("""UPDATE expenses SET amount=%s,description=%s,category=%s,expense_type=%s,created_at=%s::date+TIME '12:00'
                WHERE id=%s AND workspace_id=%s RETURNING id""",(payload.amount,payload.description.strip(),category,expense_type_for_category(category),payload.transaction_date,source_id,workspace_id)).fetchone()
        elif origin == "payroll":
            if payload.transaction_type != "income": raise HTTPException(status_code=422,detail="Las horas extra deben conservar su tipo.")
            row=conn.execute("""UPDATE payroll_events SET amount=%s,description=%s,created_at=%s::date+TIME '12:00'
                WHERE id=%s AND workspace_id=%s RETURNING id""",(payload.amount,payload.description.strip(),payload.transaction_date,source_id,workspace_id)).fetchone()
        elif origin == "transaction":
            row=conn.execute("""UPDATE transactions SET transaction_date=%s,description=%s,amount=%s,transaction_type=%s,category=%s,notes=%s
                WHERE id=%s AND workspace_id=%s AND source IN ('finva','manual','manual_expense') RETURNING id""",
                (payload.transaction_date,payload.description.strip(),payload.amount,payload.transaction_type,normalize_category(payload.category,payload.transaction_type),payload.notes,source_id,workspace_id)).fetchone()
        else:
            raise HTTPException(status_code=422,detail="Origen de movimiento inválido.")
        if not row: raise HTTPException(status_code=404,detail="Movimiento no encontrado o no editable.")
        conn.commit()
    return {"status":"ok","movement_id":movement_id}


def delete_free_movement(movement_id: str) -> dict:
    workspace_id=get_current_workspace_id()
    try:
        origin,raw_id=movement_id.split(":",1);source_id=int(raw_id)
    except (ValueError,TypeError) as exc:
        raise HTTPException(status_code=422,detail="Identificador de movimiento inválido.") from exc
    tables={"salary":"salaries","expense":"expenses","payroll":"payroll_events"}
    with get_connection() as conn:
        if origin in tables:
            row=conn.execute(f"DELETE FROM {tables[origin]} WHERE id=%s AND workspace_id=%s RETURNING id",(source_id,workspace_id)).fetchone()
        elif origin=="transaction":
            row=conn.execute("DELETE FROM transactions WHERE id=%s AND workspace_id=%s AND source IN ('finva','manual','manual_expense') RETURNING id",(source_id,workspace_id)).fetchone()
        else: raise HTTPException(status_code=422,detail="Origen de movimiento inválido.")
        if not row: raise HTTPException(status_code=404,detail="Movimiento no encontrado o no eliminable.")
        conn.commit()
    return {"status":"ok","movement_id":movement_id}
