from fastapi import APIRouter
from backend.finance.strategies import get_all_strategies
from backend.finance.strategy_rules import get_strategy_report, select_recommended_strategy
from backend.finance.allocation_engine import calculate_allocation_plan
from backend.finance.evaluators import evaluate_loan, evaluate_installment_purchase

import traceback
from fastapi import APIRouter, HTTPException

from backend.finance.models import (
    SalaryRequest,
    BonusRequest,
    DebtRequest,
    SavingRequest,
    InvestmentRequest,
    ExpenseRequest,
    EmploymentProfileRequest,
    PayrollDeductionRequest,
    PayrollEventRequest,
    ExpenseUpdateRequest,
    DebtUpdateRequest,
    DebtExtraPaymentRequest,
    DebtMonthlyPaymentRequest,
    LoanEvaluationRequest,
    InstallmentEvaluationRequest,
    PayScheduleRequest,
    CreditCardSettingsRequest,
    CardPurchaseEvaluationRequest,
)

from backend.finance.service import (
    add_salary,
    get_salaries,
    add_bonus,
    get_bonuses,
    add_debt,
    get_debts,
    add_saving,
    get_savings,
    add_investment,
    get_investments,
    add_expense,
    get_expenses,
    get_financial_summary,
    set_employment_profile,
    get_employment_profile,
    add_payroll_deduction,
    get_payroll_deductions,
    add_payroll_event,
    get_payroll_events,
    calculate_monthly_salary_projection,
    delete_expense,
    update_expense,
    delete_debt,
    update_debt,
    apply_extra_payment_to_debt,
    apply_monthly_payment_to_debt,
    get_debt_payments,
    get_net_worth_report,
    get_user_status,
    get_financial_dashboard,
    update_saving,
    delete_saving,
    update_investment,
    delete_investment,
)

from backend.finance.cashflow import (
    set_pay_schedule,
    get_pay_schedule,
    get_next_pay_date,
    get_basic_cashflow_forecast,
)

from backend.finance.card_cycle import (
    set_credit_card_settings,
    get_credit_card_settings,
    evaluate_card_purchase_date,
    evaluate_card_purchase,
)


router = APIRouter(prefix="/finance", tags=["Finance"])


@router.get("/summary")
def financial_summary():
    return get_financial_summary()

@router.get("/net-worth")
def net_worth_report():
    return get_net_worth_report()


@router.post("/salaries")
def create_salary(request: SalaryRequest):
    return add_salary(
        amount=request.amount,
        source=request.source,
    )


@router.get("/salaries")
def salaries():
    return get_salaries()


@router.post("/bonuses")
def create_bonus(request: BonusRequest):
    return add_bonus(
        amount=request.amount,
        description=request.description,
    )


@router.get("/bonuses")
def bonuses():
    return get_bonuses()


@router.post("/debts")
def create_debt(request: DebtRequest):
    return add_debt(
        name=request.name,
        debt_type=request.debt_type,
        total_amount=request.total_amount,
        remaining_amount=request.remaining_amount,
        monthly_payment=request.monthly_payment,
        interest_rate=request.interest_rate,
        term_months=request.term_months,
        payment_day=request.payment_day,
    )


@router.get("/debts")
def debts():
    return get_debts()

@router.delete("/debts/{debt_id}")
def remove_debt(debt_id: int):
    return delete_debt(debt_id)


@router.put("/debts/{debt_id}")
def edit_debt(debt_id: int, request: DebtUpdateRequest):
    return update_debt(
        debt_id=debt_id,
        name=request.name,
        debt_type=request.debt_type,
        total_amount=request.total_amount,
        remaining_amount=request.remaining_amount,
        monthly_payment=request.monthly_payment,
        interest_rate=request.interest_rate,
        term_months=request.term_months,
        payment_day=request.payment_day,
    )


@router.patch("/debts/{debt_id}/extra-payment")
def extra_payment_to_debt(debt_id: int, request: DebtExtraPaymentRequest):
    return apply_extra_payment_to_debt(
        debt_id=debt_id,
        amount=request.amount,
        new_remaining_amount=request.new_remaining_amount,
        new_monthly_payment=request.new_monthly_payment,
        description=request.description,
    )

@router.patch("/debts/{debt_id}/monthly-payment")
def monthly_payment_to_debt(debt_id: int, request: DebtMonthlyPaymentRequest):
    return apply_monthly_payment_to_debt(
        debt_id=debt_id,
        amount=request.amount,
        new_remaining_amount=request.new_remaining_amount,
        new_monthly_payment=request.new_monthly_payment,
        description=request.description,
    )


@router.get("/debt-payments")
def debt_payments():
    return get_debt_payments()


@router.get("/debts/{debt_id}/payments")
def debt_payment_history(debt_id: int):
    return get_debt_payments(debt_id)


@router.post("/savings")
def create_saving(request: SavingRequest):
    return add_saving(
        name=request.name,
        amount=request.amount,
    )


@router.get("/savings")
def savings():
    return get_savings()

@router.put("/savings/{saving_id}")
def edit_saving(
    saving_id: int,
    request: SavingRequest
):
    return update_saving(
        saving_id=saving_id,
        name=request.name,
        amount=request.amount,
    )


@router.delete("/savings/{saving_id}")
def remove_saving(saving_id: int):
    return delete_saving(saving_id)


@router.post("/investments")
def create_investment(request: InvestmentRequest):
    return add_investment(
        name=request.name,
        amount=request.amount,
    )


@router.get("/investments")
def investments():
    return get_investments()

@router.put("/investments/{investment_id}")
def edit_investment(
    investment_id: int,
    request: InvestmentRequest
):
    return update_investment(
        investment_id=investment_id,
        name=request.name,
        amount=request.amount,
    )


@router.delete("/investments/{investment_id}")
def remove_investment(investment_id: int):
    return delete_investment(investment_id)

@router.get("/expenses")
def expenses():
    return get_expenses()

@router.post("/expenses")
def create_expense(request: ExpenseRequest):
    return add_expense(
        category=request.category,
        amount=request.amount,
        expense_type=request.expense_type,
        description=request.description,
    )

@router.delete("/expenses/{expense_id}")
def remove_expense(expense_id: int):
    return delete_expense(expense_id)


@router.put("/expenses/{expense_id}")
def edit_expense(expense_id: int, request: ExpenseUpdateRequest):
    return update_expense(
        expense_id=expense_id,
        category=request.category,
        amount=request.amount,
        expense_type=request.expense_type,
        description=request.description,
    )

@router.post("/employment-profile")
def create_employment_profile(request: EmploymentProfileRequest):
    return set_employment_profile(
        hourly_rate=request.hourly_rate,
        regular_hours_per_week=request.regular_hours_per_week,
        overtime_multiplier=request.overtime_multiplier,
        holiday_multiplier=request.holiday_multiplier,
    )

@router.get("/employment-profile")
def employment_profile():
    return get_employment_profile()


@router.post("/payroll-deductions")
def create_payroll_deduction(request: PayrollDeductionRequest):
    return add_payroll_deduction(
        name=request.name,
        deduction_type=request.deduction_type,
        amount=request.amount,
        frequency=request.frequency,
    )


@router.get("/payroll-deductions")
def payroll_deductions():
    return get_payroll_deductions()


@router.post("/payroll-events")
def create_payroll_event(request: PayrollEventRequest):
    return add_payroll_event(
        event_type=request.event_type,
        hours=request.hours,
        description=request.description,
    )


@router.get("/payroll-events")
def payroll_events():
    return get_payroll_events()


@router.get("/salary-projection")
def salary_projection():
    return calculate_monthly_salary_projection()

@router.get("/strategies")
def strategies():
    return get_all_strategies()


@router.get("/strategies/recommended")
def recommended_strategy():
    return select_recommended_strategy()


@router.get("/strategies/report")
def strategy_report():
    return get_strategy_report()

@router.get("/allocation-plan")
def allocation_plan():
    return calculate_allocation_plan()

@router.post("/evaluate-loan")
def loan_evaluation(request: LoanEvaluationRequest):
    return evaluate_loan(
    amount=request.amount,
    monthly_payment=request.monthly_payment,
    purpose=request.purpose,
)


@router.post("/evaluate-installment-purchase")
def installment_purchase_evaluation(request: InstallmentEvaluationRequest):
    return evaluate_installment_purchase(
    amount=request.amount,
    month_options=request.month_options,
    purpose=request.purpose,
)

@router.post("/pay-schedule")
def create_pay_schedule(request: PayScheduleRequest):
    return set_pay_schedule(
        pay_frequency=request.pay_frequency,
        pay_day=request.pay_day,
        first_pay_date=request.first_pay_date,
        notes=request.notes,
    )


@router.get("/pay-schedule")
def pay_schedule():
    return get_pay_schedule()


@router.get("/cashflow/next-pay-date")
def next_pay_date():
    return get_next_pay_date()


@router.get("/cashflow/forecast")
def cashflow_forecast():
    return get_basic_cashflow_forecast()

@router.post("/credit-card-settings")
def create_credit_card_settings(
    request: CreditCardSettingsRequest
):
    return set_credit_card_settings(
        name=request.name,
        cut_day=request.cut_day,
        payment_day=request.payment_day,
    )


@router.get("/credit-card-settings")
def credit_card_settings():
    return get_credit_card_settings()


@router.get("/credit-card-cycle")
def credit_card_cycle():
    return evaluate_card_purchase_date()

@router.post("/credit-card/evaluate-purchase")
def card_purchase_evaluation(request: CardPurchaseEvaluationRequest):
    return evaluate_card_purchase(
        amount=request.amount,
        description=request.description,
    )

@router.get("/user-status")
def user_status():
    return get_user_status()

@router.get("/dashboard")
def financial_dashboard():
    return get_financial_dashboard()
    
@router.get("/dashboard-debug")
def financial_dashboard_debug():
    steps = {}

    try:
        steps["current_user"] = "START"
        from backend.auth.current_user import get_current_user
        steps["user"] = get_current_user()
        steps["current_user"] = "OK"

        steps["financial_summary"] = "START"
        summary = get_financial_summary()
        steps["financial_summary"] = "OK"

        steps["net_worth"] = "START"
        net_worth = get_net_worth_report()
        steps["net_worth"] = "OK"

        steps["user_status"] = "START"
        user_status = get_user_status()
        steps["user_status"] = "OK"

        steps["dashboard"] = "START"
        dashboard = get_financial_dashboard()
        steps["dashboard"] = "OK"

        return {
            "status": "OK",
            "steps": steps,
            "summary": summary,
            "net_worth": net_worth,
            "user_status": user_status,
            "dashboard": dashboard,
        }

    except Exception as error:
        return {
            "status": "ERROR",
            "error_type": type(error).__name__,
            "error": str(error),
            "steps": steps,
        }