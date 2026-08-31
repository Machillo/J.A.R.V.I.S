from fastapi import APIRouter

from backend.auth.saas import require_feature
from backend.user_product.models import (
    BasicSimulationRequest, DebtPaymentRequest, ExpenseCreateRequest, FinancialSituationRequest,
    GoalCreateRequest, IncomeCreateRequest, OvertimeCreateRequest, TransactionCreateRequest,
    UserDebtCreateRequest, VipSimulationRequest,
)
from backend.user_product.service import (
    create_expense_entry, create_income, create_overtime, create_user_debt, create_user_goal,
    create_user_transaction, delete_user_debt, delete_user_goal, delete_user_transaction,
    get_financial_situation, get_strategy_basic, get_strategy_vip, get_user_finance_summary,
    list_expenses, list_income, list_overtime, list_user_debts, list_user_goals, list_user_transactions,
    pay_user_debt, simulate_strategy_vip, update_financial_situation,
)

router = APIRouter(prefix="/user-product", tags=["Finva Product"])

@router.get("/finance/summary")
def finance_summary():
    require_feature("finance_overview"); return get_user_finance_summary()

@router.get("/finance/income")
def income_list():
    require_feature("spending"); return list_income()

@router.post("/finance/income")
def income_create(request: IncomeCreateRequest):
    require_feature("spending"); return create_income(request)

@router.get("/finance/expenses")
def expenses_list():
    require_feature("spending"); return list_expenses()

@router.post("/finance/expenses")
def expenses_create(request: ExpenseCreateRequest):
    require_feature("spending"); return create_expense_entry(request)

@router.get("/finance/overtime")
def overtime_list():
    require_feature("overtime"); return list_overtime()

@router.post("/finance/overtime")
def overtime_create(request: OvertimeCreateRequest):
    require_feature("overtime"); return create_overtime(request)

@router.get("/finance/debts")
def debts_list():
    require_feature("debts"); return list_user_debts()

@router.post("/finance/debts")
def debts_create(request: UserDebtCreateRequest):
    require_feature("debts"); return create_user_debt(request)

@router.delete("/finance/debts/{debt_id}")
def debts_delete(debt_id: int):
    require_feature("debts"); return delete_user_debt(debt_id)

@router.post("/finance/debts/{debt_id}/payments")
def debt_payment(debt_id: int, request: DebtPaymentRequest):
    require_feature("debts"); return pay_user_debt(debt_id, request.amount)

@router.get("/goals")
def goals_list():
    require_feature("goals"); return list_user_goals()

@router.post("/goals")
def goals_create(request: GoalCreateRequest):
    require_feature("goals"); return create_user_goal(request)

@router.delete("/goals/{goal_id}")
def goals_delete(goal_id: int):
    require_feature("goals"); return delete_user_goal(goal_id)

@router.get("/transactions")
def transactions_list():
    require_feature("transactions"); return list_user_transactions()

@router.post("/transactions")
def transactions_create(request: TransactionCreateRequest):
    require_feature("transactions"); return create_user_transaction(request)

@router.delete("/transactions/{transaction_id}")
def transactions_delete(transaction_id: int):
    require_feature("transactions"); return delete_user_transaction(transaction_id)

@router.get("/financial-situation")
def financial_situation():
    require_feature("finance_overview"); return get_financial_situation()

@router.put("/financial-situation")
def financial_situation_update(request: FinancialSituationRequest):
    require_feature("finance_overview"); return update_financial_situation(request)

@router.get("/finance/strategy-basic")
def strategy_basic():
    require_feature("strategy_basic"); return get_strategy_basic()

@router.post("/finance/strategy-basic/simulate")
def strategy_basic_simulate(request: BasicSimulationRequest):
    require_feature("strategy_basic"); return get_strategy_basic(request.extra_monthly)

@router.get("/finance/strategy-vip")
def strategy_vip():
    require_feature("strategy_vip"); return get_strategy_vip()

@router.post("/finance/strategy-vip/simulate")
def strategy_vip_simulate(request: VipSimulationRequest):
    require_feature("strategy_vip")
    return simulate_strategy_vip(request.monthly_income_change, request.monthly_expense_change, request.one_time_extra)
