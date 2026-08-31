from fastapi import APIRouter

from backend.user_product.models import (
    BasicSimulationRequest,
    DebtPaymentRequest,
    ExpenseCreateRequest,
    FinancialSituationRequest,
    IncomeCreateRequest,
    OvertimeCreateRequest,
    UserDebtCreateRequest,
    VipSimulationRequest,
)
from backend.user_product.service import (
    create_expense_entry,
    create_income,
    create_overtime,
    create_user_debt,
    get_financial_situation,
    get_strategy_basic,
    get_strategy_vip,
    get_user_finance_summary,
    list_expenses,
    list_income,
    list_overtime,
    pay_user_debt,
    simulate_strategy_vip,
    update_financial_situation,
)

router = APIRouter(prefix="/user-product", tags=["Users Product"])


@router.get("/finance/summary")
def finance_summary():
    return get_user_finance_summary()


@router.get("/finance/income")
def income_list():
    return list_income()


@router.post("/finance/income")
def income_create(request: IncomeCreateRequest):
    return create_income(request)


@router.get("/finance/expenses")
def expenses_list():
    return list_expenses()


@router.post("/finance/expenses")
def expenses_create(request: ExpenseCreateRequest):
    return create_expense_entry(request)


@router.get("/finance/overtime")
def overtime_list():
    return list_overtime()


@router.post("/finance/overtime")
def overtime_create(request: OvertimeCreateRequest):
    return create_overtime(request)


@router.post("/finance/debts")
def debts_create(request: UserDebtCreateRequest):
    return create_user_debt(request)


@router.post("/finance/debts/{debt_id}/payments")
def debt_payment(debt_id: int, request: DebtPaymentRequest):
    return pay_user_debt(debt_id, request.amount)


@router.get("/financial-situation")
def financial_situation():
    return get_financial_situation()


@router.put("/financial-situation")
def financial_situation_update(request: FinancialSituationRequest):
    return update_financial_situation(request)


@router.get("/finance/strategy-basic")
def strategy_basic():
    return get_strategy_basic()


@router.post("/finance/strategy-basic/simulate")
def strategy_basic_simulate(request: BasicSimulationRequest):
    return get_strategy_basic(request.extra_monthly)


@router.get("/finance/strategy-vip")
def strategy_vip():
    return get_strategy_vip()


@router.post("/finance/strategy-vip/simulate")
def strategy_vip_simulate(request: VipSimulationRequest):
    return simulate_strategy_vip(
        request.monthly_income_change,
        request.monthly_expense_change,
        request.one_time_extra,
    )
