from fastapi import APIRouter

from backend.auth.plans import require_feature
from backend.finance.models import DebtPaymentRequest, DebtRequest, DebtUpdateRequest, MoneyEntryRequest, OvertimeRequest, StrategySimulationRequest
from backend.finance.service import (
    add_debt,
    add_expense,
    add_income,
    add_overtime,
    delete_debt,
    get_debts,
    get_expenses,
    get_income,
    get_overtime,
    get_strategy_basic,
    get_strategy_vip,
    get_summary,
    register_debt_payment,
    update_debt,
)


router = APIRouter(prefix="/finance", tags=["Finance"])


@router.get("/summary")
def summary():
    return get_summary()


@router.get("/income")
def income():
    return get_income()


@router.post("/income")
def create_income(request: MoneyEntryRequest):
    return add_income(request.amount, request.description, request.category, request.entry_date)


@router.get("/expenses")
def expenses():
    return get_expenses()


@router.post("/expenses")
def create_expense(request: MoneyEntryRequest):
    return add_expense(request.amount, request.description, request.category, request.entry_date)


@router.get("/overtime")
def overtime():
    return get_overtime()


@router.post("/overtime")
def create_overtime(request: OvertimeRequest):
    return add_overtime(request.hours, request.hourly_rate, request.multiplier, request.work_date, request.notes)


@router.get("/debts")
def debts():
    return get_debts()


@router.post("/debts")
def create_debt(request: DebtRequest):
    return add_debt(**request.model_dump())


@router.put("/debts/{debt_id}")
def edit_debt(debt_id: int, request: DebtUpdateRequest):
    return update_debt(debt_id, **request.model_dump())


@router.delete("/debts/{debt_id}")
def remove_debt(debt_id: int):
    return delete_debt(debt_id)


@router.post("/debts/{debt_id}/payments")
def debt_payment(debt_id: int, request: DebtPaymentRequest):
    return register_debt_payment(debt_id, request.amount, request.payment_date, request.notes)


@router.get("/strategy-basic")
def strategy_basic():
    require_feature("strategy_basic")
    return get_strategy_basic()


@router.post("/strategy-basic/simulate")
def strategy_basic_simulate(request: StrategySimulationRequest):
    require_feature("strategy_basic")
    return get_strategy_basic(extra_monthly=request.extra_monthly)


@router.get("/strategy-vip")
def strategy_vip():
    require_feature("strategy_vip")
    return get_strategy_vip()
