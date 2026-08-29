from datetime import date
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException

from backend.auth.current_user import get_current_user_id, get_current_workspace_id
from backend.core.database import get_connection, serialize_row, serialize_rows

router = APIRouter(prefix="/finance/business-center", tags=["finance-businesses"])

class BusinessRequest(BaseModel):
    name: str
    description: Optional[str] = None
    ownership_pct: float = Field(default=100, ge=0, le=100)

class BusinessMovementRequest(BaseModel):
    business_id: int
    movement_type: str
    amount: float = Field(gt=0)
    movement_date: Optional[date] = None
    description: str
    category: Optional[str] = None


def _ensure_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS business_projects (
          id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL DEFAULT 1, workspace_id UUID, name TEXT NOT NULL,
          description TEXT, ownership_pct NUMERIC(6,2) NOT NULL DEFAULT 100,
          status TEXT NOT NULL DEFAULT 'active', created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS business_movements (
          id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL DEFAULT 1, workspace_id UUID,
          business_id BIGINT NOT NULL REFERENCES business_projects(id) ON DELETE CASCADE,
          movement_date DATE NOT NULL DEFAULT CURRENT_DATE, movement_type TEXT NOT NULL,
          amount NUMERIC(14,2) NOT NULL, description TEXT NOT NULL, category TEXT,
          transaction_id BIGINT, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

@router.get("")
def get_business_center():
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        _ensure_tables(conn)
        businesses = conn.execute("SELECT * FROM business_projects WHERE workspace_id=%s ORDER BY status, name", (workspace_id,)).fetchall()
        movements = conn.execute("SELECT * FROM business_movements WHERE workspace_id=%s ORDER BY movement_date DESC,id DESC LIMIT 200", (workspace_id,)).fetchall()
        totals = conn.execute("""
          SELECT
            COALESCE(SUM(CASE WHEN movement_type='income' THEN amount ELSE 0 END),0) income,
            COALESCE(SUM(CASE WHEN movement_type='expense' THEN amount ELSE 0 END),0) expenses,
            COALESCE(SUM(CASE WHEN movement_type='capital' THEN amount ELSE 0 END),0) capital
          FROM business_movements WHERE workspace_id=%s
        """, (workspace_id,)).fetchone()
        conn.commit()
    t = serialize_row(totals) or {}
    income, expenses = float(t.get('income') or 0), float(t.get('expenses') or 0)
    return {"businesses": serialize_rows(businesses), "movements": serialize_rows(movements),
            "income": income, "expenses": expenses, "profit": round(income-expenses,2),
            "capital": float(t.get('capital') or 0)}

@router.post("/businesses")
def create_business(request: BusinessRequest):
    user_id = get_current_user_id()  # legacy compatibility during migration
    workspace_id = get_current_workspace_id()
    with get_connection() as conn:
        _ensure_tables(conn)
        row = conn.execute("""INSERT INTO business_projects(user_id,workspace_id,name,description,ownership_pct)
          VALUES(%s,%s,%s,%s,%s) RETURNING *""", (user_id, workspace_id, request.name.strip(), request.description, request.ownership_pct)).fetchone()
        conn.commit()
    return serialize_row(row)

@router.post("/movements")
def add_business_movement(request: BusinessMovementRequest):
    user_id = get_current_user_id()  # legacy compatibility during migration
    workspace_id = get_current_workspace_id()
    kind = request.movement_type.lower().strip()
    if kind not in {'income','expense','capital'}:
        raise HTTPException(400, "movement_type debe ser income, expense o capital")
    movement_date = request.movement_date or date.today()
    with get_connection() as conn:
        _ensure_tables(conn)
        business = conn.execute("SELECT * FROM business_projects WHERE id=%s AND workspace_id=%s", (request.business_id,workspace_id)).fetchone()
        if not business: raise HTTPException(404, "Negocio no encontrado")
        transaction_id = None
        if kind in {'income','expense'}:
            tx_type = 'income' if kind == 'income' else 'expense'
            category = request.category or ('Ingresos de negocio' if kind == 'income' else 'Negocio')
            tx = conn.execute("""INSERT INTO transactions(user_id,workspace_id,transaction_date,description,amount,transaction_type,category,source,notes)
              VALUES(%s,%s,%s,%s,%s,%s,%s,'business_center',%s) RETURNING id""",
              (user_id, workspace_id, str(movement_date), request.description, request.amount, tx_type, category,
               f"business_id:{request.business_id}; business:{business['name']}")).fetchone()
            transaction_id = tx['id']
        row = conn.execute("""INSERT INTO business_movements(user_id,workspace_id,business_id,movement_date,movement_type,amount,description,category,transaction_id)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
          (user_id,workspace_id,request.business_id,movement_date,kind,request.amount,request.description,request.category,transaction_id)).fetchone()
        conn.commit()
    return serialize_row(row)
