from fastapi import APIRouter, Header, HTTPException, Query

from backend.auth.saas import require_feature
from backend.user_product.models import (
    BasicSimulationRequest, BudgetUpdateRequest, DebtPaymentRequest, ExpenseCreateRequest, ExpenseUpdateRequest,
    FinancialSituationRequest, GoalContributionRequest, GoalCreateRequest, GoalUpdateRequest, IncomeCreateRequest,
    FinancialAccountIdentityRequest, GmailCandidateReviewRequest, GmailConsentRequest, OwnTransferConfirmRequest, IncomeUpdateRequest, MovementUpdateRequest, RecurringItemRequest, TransactionCreateRequest,
    SavingsPlanContributionRequest, SavingsPlanCreateRequest, SavingsPlanUpdateRequest,
    UserDebtCreateRequest, UserDebtUpdateRequest, VipSimulationRequest,
)
from backend.user_product.service import (
    create_expense_entry, create_income, create_user_debt, create_user_goal,
    create_user_transaction, delete_expense, delete_income, delete_user_debt, delete_user_goal, delete_user_transaction,
    get_financial_situation, get_strategy_basic, get_strategy_vip, get_user_finance_summary,
    list_expenses, list_income, list_user_debts, list_user_goals, list_user_transactions,
    pay_user_debt, simulate_strategy_vip, update_expense, update_financial_situation, update_income,
    update_user_debt, update_user_goal, contribute_user_goal, create_savings_plan,
    delete_savings_plan, contribute_savings_plan, list_savings_plans, update_savings_plan,
)
from backend.user_product.basic_service import (
    create_recurring_item, delete_recurring_item, get_basic_dashboard, get_basic_report,
    get_financial_calendar, get_guided_budget, list_recurring_items, save_guided_budget,
    update_recurring_item,
)
from backend.user_product.free_service import (
    delete_free_movement, get_free_dashboard, get_free_monthly_summary,
    list_free_movements, update_free_movement,
)
from backend.user_product.vip_service import get_vip_command_center
from backend.ai.strategy_dashboard import get_premium_strategy_dashboard
from backend.finance.emergency_fund import get_salvavidas_state, update_salvavidas
from backend.finance.intelligence import get_debt_advisory
from backend.finance.models import SalvavidasUpdateRequest
from backend.finance.strategic_engine import calculate_debt_strategies
from backend.finance.service import calculate_aguinaldo
from backend.user_product.gmail_service import (
    begin_gmail_connection,
    disconnect_gmail,
    finish_gmail_connection,
    gmail_maintenance,
    gmail_status,
    list_gmail_emails,
    process_gmail_push,
    review_gmail_candidate,
    sync_current_gmail,
)
from backend.user_product.financial_identity import confirm_financial_account, list_financial_identity
from backend.user_product.own_transfer_review import confirm_own_transfer, list_own_transfer_suggestions
from backend.user_product.trust_analytics import get_gmail_trust_analytics
from backend.user_product.gmail_consent import accept_gmail_consent

router = APIRouter(prefix="/user-product", tags=["DINCR Product"])

@router.get("/finance/summary")
def finance_summary():
    require_feature("finance_overview"); return get_user_finance_summary()

@router.get("/finance/income")
def income_list():
    require_feature("spending"); return list_income()

@router.post("/finance/income")
def income_create(request: IncomeCreateRequest):
    require_feature("spending"); return create_income(request)

@router.put("/finance/income/{income_id}")
def income_update(income_id: int, request: IncomeUpdateRequest):
    require_feature("spending"); return update_income(income_id, request)

@router.delete("/finance/income/{income_id}")
def income_delete(income_id: int):
    require_feature("spending"); return delete_income(income_id)

@router.get("/finance/expenses")
def expenses_list():
    require_feature("spending"); return list_expenses()

@router.post("/finance/expenses")
def expenses_create(request: ExpenseCreateRequest):
    require_feature("spending"); return create_expense_entry(request)

@router.put("/finance/expenses/{expense_id}")
def expenses_update(expense_id: int, request: ExpenseUpdateRequest):
    require_feature("spending"); return update_expense(expense_id, request)

@router.delete("/finance/expenses/{expense_id}")
def expenses_delete(expense_id: int):
    require_feature("spending"); return delete_expense(expense_id)

@router.get("/finance/debts")
def debts_list():
    require_feature("debts"); return list_user_debts()

@router.post("/finance/debts")
def debts_create(request: UserDebtCreateRequest):
    require_feature("debts"); return create_user_debt(request)

@router.put("/finance/debts/{debt_id}")
def debts_update(debt_id: int, request: UserDebtUpdateRequest):
    require_feature("strategy_basic"); return update_user_debt(debt_id, request)

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

@router.put("/goals/{goal_id}")
def goals_update(goal_id: int, request: GoalUpdateRequest):
    require_feature("strategy_basic"); return update_user_goal(goal_id, request)

@router.post("/goals/{goal_id}/contributions")
def goals_contribute(goal_id: int, request: GoalContributionRequest):
    require_feature("goals"); return contribute_user_goal(goal_id, request)

@router.delete("/goals/{goal_id}")
def goals_delete(goal_id: int):
    require_feature("goals"); return delete_user_goal(goal_id)

@router.get("/savings-plans")
def savings_plans_list():
    require_feature("goals"); return list_savings_plans()

@router.post("/savings-plans")
def savings_plans_create(request: SavingsPlanCreateRequest):
    require_feature("goals"); return create_savings_plan(request)

@router.put("/savings-plans/{plan_id}")
def savings_plans_update(plan_id: int, request: SavingsPlanUpdateRequest):
    require_feature("goals"); return update_savings_plan(plan_id, request)

@router.post("/savings-plans/{plan_id}/contributions")
def savings_plans_contribute(plan_id: int, request: SavingsPlanContributionRequest):
    require_feature("goals"); return contribute_savings_plan(plan_id, request)

@router.delete("/savings-plans/{plan_id}")
def savings_plans_delete(plan_id: int):
    require_feature("goals"); return delete_savings_plan(plan_id)

@router.get("/transactions")
def transactions_list():
    require_feature("transactions"); return list_user_transactions()

@router.post("/transactions")
def transactions_create(request: TransactionCreateRequest):
    require_feature("transactions"); return create_user_transaction(request)

@router.delete("/transactions/{transaction_id}")
def transactions_delete(transaction_id: int):
    require_feature("transactions"); return delete_user_transaction(transaction_id)

@router.get("/free/dashboard")
def free_dashboard():
    require_feature("finance_overview"); return get_free_dashboard()

@router.get("/free/monthly-summary")
def free_monthly_summary(period: str | None = None):
    require_feature("finance_overview"); return get_free_monthly_summary(period)

@router.get("/free/movements")
def free_movements():
    require_feature("transactions"); return list_free_movements()

@router.put("/free/movements/{movement_id}")
def free_movement_update(movement_id: str, request: MovementUpdateRequest):
    require_feature("transactions"); return update_free_movement(movement_id, request)

@router.delete("/free/movements/{movement_id}")
def free_movement_delete(movement_id: str):
    require_feature("transactions"); return delete_free_movement(movement_id)

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

@router.get("/vip/command-center")
def vip_command_center():
    require_feature("strategy_vip"); return get_vip_command_center()

@router.get("/vip/strategy-dashboard")
def vip_strategy_dashboard():
    """Motor determinístico probado en JARVIS, aislado al workspace DINCR activo."""
    require_feature("strategy_vip"); return get_premium_strategy_dashboard()

@router.get("/vip/debt-advisory")
def vip_debt_advisory(extra_cash: float | None = None):
    require_feature("strategy_vip"); return get_debt_advisory(extra_cash=extra_cash)

@router.get("/vip/debt-strategies")
def vip_debt_strategies():
    require_feature("strategy_vip"); return calculate_debt_strategies()

@router.get("/vip/salvavidas")
def vip_salvavidas():
    require_feature("strategy_vip"); return get_salvavidas_state()

@router.put("/vip/salvavidas")
def vip_salvavidas_update(request: SalvavidasUpdateRequest):
    require_feature("strategy_vip"); return update_salvavidas(**request.model_dump(exclude_unset=True))

@router.get("/vip/aguinaldo")
def vip_aguinaldo():
    require_feature("gmail_automation")
    if not gmail_status().get("connected"):
        raise HTTPException(status_code=409, detail="Debes sincronizar tu email para calcular el aguinaldo.")
    return calculate_aguinaldo()

@router.get("/vip/gmail/status")
def vip_gmail_status():
    require_feature("gmail_automation"); return gmail_status()

@router.post("/vip/gmail/connect")
def vip_gmail_connect():
    require_feature("gmail_automation"); return begin_gmail_connection()

@router.post("/vip/gmail/consent")
def vip_gmail_consent(request: GmailConsentRequest):
    require_feature("gmail_automation")
    return accept_gmail_consent(accepted=request.accepted, version=request.version)

@router.get("/vip/gmail/callback")
def vip_gmail_callback(code: str | None = None, state: str | None = None, error: str | None = None):
    return finish_gmail_connection(code=code, state=state, error=error)

@router.post("/vip/gmail/sync")
def vip_gmail_sync():
    require_feature("gmail_automation"); return sync_current_gmail()

@router.get("/vip/gmail/emails")
def vip_gmail_emails(status: str | None = None):
    require_feature("gmail_automation"); return list_gmail_emails(status)

@router.get("/vip/gmail/own-transfer-suggestions")
def vip_own_transfer_suggestions():
    require_feature("gmail_automation"); return list_own_transfer_suggestions()

@router.post("/vip/gmail/candidates/{candidate_id}/own-transfer")
def vip_confirm_own_transfer(candidate_id: int, request: OwnTransferConfirmRequest):
    require_feature("gmail_automation")
    return confirm_own_transfer(candidate_id, request.counterpart_id, request.unknown_direction)

@router.get("/vip/gmail/trust-analytics")
def vip_gmail_trust_analytics():
    require_feature("gmail_automation"); return get_gmail_trust_analytics()

@router.get("/vip/financial-identity")
def vip_financial_identity():
    require_feature("gmail_automation"); return list_financial_identity()

@router.put("/vip/financial-identity/accounts/{account_balance_id}")
def vip_financial_identity_confirm(account_balance_id: int, request: FinancialAccountIdentityRequest):
    require_feature("gmail_automation")
    return confirm_financial_account(account_balance_id, request.ownership_status, request.display_name)

@router.post("/vip/gmail/candidates/{candidate_id}/accept")
def vip_gmail_candidate_accept(candidate_id: int):
    require_feature("gmail_automation"); return review_gmail_candidate(candidate_id, "accept")

@router.post("/vip/gmail/candidates/{candidate_id}/reject")
def vip_gmail_candidate_reject(candidate_id: int):
    require_feature("gmail_automation"); return review_gmail_candidate(candidate_id, "reject")

@router.put("/vip/gmail/candidates/{candidate_id}/accept")
def vip_gmail_candidate_correct(candidate_id: int, request: GmailCandidateReviewRequest):
    require_feature("gmail_automation")
    return review_gmail_candidate(candidate_id, "accept", request.model_dump())

@router.delete("/vip/gmail")
def vip_gmail_disconnect(connection_id: int | None = None):
    require_feature("gmail_automation"); return disconnect_gmail(connection_id)

@router.post("/vip/gmail/maintenance")
def vip_gmail_maintenance(x_finva_cron_secret: str | None = Header(default=None)):
    return gmail_maintenance(x_finva_cron_secret)

@router.post("/vip/gmail/push")
def vip_gmail_push(payload: dict, token: str | None = Query(default=None)):
    return process_gmail_push(payload, token)

@router.get("/basic/dashboard")
def basic_dashboard():
    require_feature("basic_dashboard"); return get_basic_dashboard()

@router.get("/basic/budget")
def basic_budget():
    require_feature("guided_budget"); return get_guided_budget()

@router.put("/basic/budget")
def basic_budget_update(request: BudgetUpdateRequest):
    require_feature("guided_budget"); return save_guided_budget(request)

@router.get("/basic/calendar")
def basic_calendar(period: str | None = None):
    require_feature("financial_calendar"); return get_financial_calendar(period)

@router.get("/basic/recurring")
def recurring_list():
    require_feature("recurring_items"); return list_recurring_items()

@router.post("/basic/recurring")
def recurring_create(request: RecurringItemRequest):
    require_feature("recurring_items"); return create_recurring_item(request)

@router.put("/basic/recurring/{item_id}")
def recurring_update(item_id: int, request: RecurringItemRequest):
    require_feature("recurring_items"); return update_recurring_item(item_id, request)

@router.delete("/basic/recurring/{item_id}")
def recurring_delete(item_id: int):
    require_feature("recurring_items"); return delete_recurring_item(item_id)

@router.get("/basic/reports")
def basic_reports(period: str | None = None):
    require_feature("basic_reports"); return get_basic_report(period)
