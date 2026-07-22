from pydantic import BaseModel


class SalaryRequest(BaseModel):
    amount: float
    source: str


class BonusRequest(BaseModel):
    amount: float
    description: str = ""


class DebtRequest(BaseModel):
    name: str
    debt_type: str = "other"
    total_amount: float
    remaining_amount: float
    monthly_payment: float
    interest_rate: float = 0
    term_months: int | None = None
    payment_day: int | None = None
    first_payment_date: str | None = None
    auto_update_monthly: bool = True


class SavingRequest(BaseModel):
    name: str
    amount: float


class InvestmentRequest(BaseModel):
    name: str
    amount: float


class ExpenseRequest(BaseModel):
    category: str
    amount: float
    expense_type: str = "variable"
    description: str = ""

class EmploymentProfileRequest(BaseModel):
    hourly_rate: float
    regular_hours_per_week: float
    overtime_multiplier: float = 1.5
    holiday_multiplier: float = 2


class PayrollDeductionRequest(BaseModel):
    name: str
    deduction_type: str
    amount: float
    frequency: str


class PayrollEventRequest(BaseModel):
    event_type: str
    hours: float
    description: str = ""

class ExpenseUpdateRequest(BaseModel):
    category: str
    amount: float
    expense_type: str = "variable"
    description: str = ""

class DebtUpdateRequest(BaseModel):
    name: str
    debt_type: str = "other"
    total_amount: float
    remaining_amount: float
    monthly_payment: float
    interest_rate: float = 0
    term_months: int | None = None
    payment_day: int | None = None
    first_payment_date: str | None = None
    auto_update_monthly: bool = True


class DebtExtraPaymentRequest(BaseModel):
    amount: float
    new_remaining_amount: float | None = None
    new_monthly_payment: float | None = None
    description: str = ""

class DebtMonthlyPaymentRequest(BaseModel):
    amount: float
    new_remaining_amount: float
    new_monthly_payment: float | None = None
    description: str = ""

class LoanEvaluationRequest(BaseModel):
    amount: float
    monthly_payment: float
    purpose: str = "general"


class InstallmentEvaluationRequest(BaseModel):
    amount: float
    month_options: list[int]
    purpose: str = "general"

class PayScheduleRequest(BaseModel):
    pay_frequency: str
    pay_day: str | None = None
    first_pay_date: str | None = None
    notes: str = ""

class CreditCardSettingsRequest(BaseModel):
    name: str
    cut_day: int
    payment_day: int

class CardPurchaseEvaluationRequest(BaseModel):
    amount: float
    description: str = ""

class WhatIfSimulationRequest(BaseModel):
    amount: float
    months: int = 1
    description: str = ""
    currency: str = "CRC"
    exchange_rate: float = 1.0


class ReconciliationRequest(BaseModel):
    opening_balance: float
    current_balance: float


class FixedExpenseRequest(BaseModel):
    name: str
    category: str = "Gastos fijos"
    expected_amount: float | None = None
    currency: str = "CRC"
    frequency: str = "monthly"
    interval_months: int = 1
    start_month: str | None = None
    due_day: int | None = None
    payment_method: str = "manual"
    auto_deducted: bool = False
    aliases: list[str] = []
    notes: str = ""


class FixedExpenseUpdateRequest(BaseModel):
    name: str | None = None
    category: str | None = None
    expected_amount: float | None = None
    currency: str | None = None
    frequency: str | None = None
    interval_months: int | None = None
    start_month: str | None = None
    due_day: int | None = None
    payment_method: str | None = None
    auto_deducted: bool | None = None
    aliases: list[str] | None = None
    notes: str | None = None
    is_active: bool | None = None


class ReceivableRequest(BaseModel):
    person_name: str
    amount: float
    notes: str = ""


class ReceivablePaymentRequest(BaseModel):
    amount: float
    source_transaction_id: int | None = None
    notes: str = ""
    payment_date: str | None = None
    method: str = "manual"


class AccountBalanceRequest(BaseModel):
    account_name: str
    current_balance: float
    bank_name: str = ""
    account_last4: str = ""
    currency: str = "CRC"


class GoalPlanningRequest(BaseModel):
    description: str
    estimated_total_cost: float | None = None
