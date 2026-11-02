from datetime import date
from typing import Literal
from pydantic import BaseModel, Field, model_validator


class GmailConsentRequest(BaseModel):
    accepted: bool
    version: str = Field(max_length=80)


class MailConnectRequest(BaseModel):
    # History to import, chosen before the provider consent.
    import_scope: Literal["current_month", "current_year"] = "current_year"
    # Language the app shows (BCP 47), for the provider's consent screens. Normalized
    # to en/es server-side; any other value falls back to English.
    locale: str | None = Field(default=None, max_length=35)


class MailConnectionCompleteRequest(BaseModel):
    flow: str = Field(max_length=64)
    completion: str = Field(max_length=256)


class IncomeCreateRequest(BaseModel):
    amount: float = Field(gt=0)
    description: str = ""
    category: str = "salario"
    entry_date: date | None = None
    # Currency the amount was typed in; omitted = the account's base currency.
    # The other currency needs the user's rate (CRC per 1 USD); DINCR never invents one.
    currency: Literal["CRC", "USD"] | None = None
    exchange_rate: float | None = Field(default=None, gt=0, le=100000)


class ExpenseCreateRequest(BaseModel):
    amount: float = Field(gt=0)
    description: str = ""
    category: str = "general"
    entry_date: date | None = None
    # Currency the amount was typed in; omitted = the account's base currency.
    # The other currency needs the user's rate (CRC per 1 USD); DINCR never invents one.
    currency: Literal["CRC", "USD"] | None = None
    exchange_rate: float | None = Field(default=None, gt=0, le=100000)
    # The own account or card that paid it (expense_account); not sent = left as it is.
    financial_account_id: int | None = Field(default=None, gt=0)
    # In the other currency without a rate: it waits for the close to be converted (pending_conversion).
    convert_at_close: bool = False


class IncomeUpdateRequest(IncomeCreateRequest):
    pass


class ExpenseUpdateRequest(ExpenseCreateRequest):
    pass


class OvertimeCreateRequest(BaseModel):
    hours: float = Field(gt=0)
    hourly_rate: float = Field(gt=0)
    multiplier: float = Field(default=1.5, gt=0)
    work_date: date | None = None
    notes: str = ""


class UserDebtCreateRequest(BaseModel):
    name: str
    total_amount: float | None = Field(default=None, ge=0)
    remaining_amount: float = Field(ge=0)
    monthly_payment: float | None = Field(default=None, ge=0)
    interest_rate: float | None = Field(default=None, ge=0)
    payment_day: int | None = Field(default=None, ge=1, le=31)
    debt_type: str = "other"
    term_months: int | None = Field(default=None, gt=0)
    next_payment_date: str | None = None


class UserDebtUpdateRequest(UserDebtCreateRequest):
    # True when the user typed or confirmed the rate in this edit. Saving the rest of the debt
    # with the rate it was loaded with never confirms it (UNKNOWN ≠ 0%, see debt_rates.py).
    interest_rate_confirmed: bool | None = None


class DebtPaymentRequest(BaseModel):
    amount: float = Field(gt=0)
    # What the bank did with an extra amount, as the user says it (one or none).
    remaining_installments: int | None = Field(default=None, ge=1, le=600)
    new_monthly_payment: float | None = Field(default=None, gt=0)
    # "El banco me avisa después": the day to be reminded (debt_after_extra).
    remind_on: date | None = None

    @model_validator(mode="after")
    def one_adjustment(self):
        given = [self.remaining_installments is not None, self.new_monthly_payment is not None, self.remind_on is not None]
        if sum(given) > 1:
            raise ValueError("Indicá una sola respuesta: las cuotas que quedan, la cuota nueva o el día del recordatorio.")
        return self


class DebtAfterExtraRequest(BaseModel):
    """The bank's answer after an extra payment, or a new day to be reminded (debt_after_extra)."""
    remaining_installments: int | None = None
    new_monthly_payment: float | None = None
    unchanged: bool = False
    remind_on: date | None = None


class GoalContributionRequest(BaseModel):
    amount: float = Field(gt=0)
    contribution_date: date | None = None


class BasicSimulationRequest(BaseModel):
    extra_monthly: float = Field(default=0, ge=0)


class DebtScenarioRequest(BaseModel):
    """A debt what-if (debt_scenarios.py): pay one off, an extra payment to one, a new debt, refinance
    one (`debt_id`, new `annual_rate` and `term_months`, optional fee as `amount`) or consolidate
    several (`debt_ids`, same terms)."""
    kind: Literal["pay_off", "extra_payment", "new_debt", "refinance", "consolidate"]
    debt_id: int | None = Field(default=None, gt=0)
    amount: float | None = Field(default=None, gt=0, le=1_000_000_000_000, allow_inf_nan=False)
    monthly_payment: float | None = Field(default=None, gt=0, le=1_000_000_000_000, allow_inf_nan=False)
    annual_rate: float | None = Field(default=None, ge=0, le=500, allow_inf_nan=False)
    term_months: int | None = Field(default=None, gt=0, le=600)
    name: str | None = Field(default=None, max_length=80)
    debt_ids: list[int] | None = Field(default=None, max_length=50)


class VipSimulationRequest(BaseModel):
    monthly_income_change: float = 0
    monthly_expense_change: float = 0
    one_time_extra: float = Field(default=0, ge=0)


class FinancialSituationRequest(BaseModel):
    income_type: Literal["fixed", "hourly"]
    fixed_monthly_salary: float | None = Field(default=None, gt=0)
    hourly_rate: float | None = Field(default=None, gt=0)
    work_days_per_week: int = Field(ge=1, le=7)
    hours_per_day: float | None = Field(default=None, gt=0, le=24)
    pay_frequency: Literal["weekly", "biweekly", "monthly"]
    payday_note: str | None = Field(default=None, max_length=80)
    essential_monthly_expenses: float | None = Field(default=None, ge=0)
    liquid_savings: float | None = Field(default=None, ge=0)
    emergency_fund_target: float | None = Field(default=None, ge=0)
    strategy_preference: Literal["debt", "emergency", "goals", "balanced"] | None = None
    discretionary_monthly_minimum: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_income(self):
        if self.income_type == "fixed" and self.fixed_monthly_salary is None:
            raise ValueError("Indicá el salario que realmente te llega al mes.")
        if self.income_type == "hourly" and (self.hourly_rate is None or self.hours_per_day is None):
            raise ValueError("Indicá cuánto te pagan por hora y cuántas horas trabajás normalmente por día.")
        return self


class GoalCreateRequest(BaseModel):
    name: str
    target_amount: float = Field(gt=0)
    current_amount: float = Field(default=0, ge=0)
    target_date: date | None = None
    priority: str = "medium"


class GoalUpdateRequest(GoalCreateRequest):
    status: Literal["active", "paused", "completed"] = "active"


class GoalContributionRequest(BaseModel):
    amount: float = Field(gt=0)
    contribution_date: str | None = None


class SavingsPlanCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    monthly_amount: float = Field(gt=0)
    saved_amount: float = Field(default=0, ge=0)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_dates(self):
        if self.end_date < self.start_date:
            raise ValueError("La fecha final debe ser igual o posterior a la fecha inicial.")
        return self


class SavingsPlanUpdateRequest(SavingsPlanCreateRequest):
    status: Literal["active", "paused", "completed"] = "active"


class SavingsPlanContributionRequest(BaseModel):
    amount: float = Field(gt=0)
    contribution_date: date | None = None


class BudgetItemRequest(BaseModel):
    category: str
    monthly_limit: float = Field(ge=0)


class BudgetUpdateRequest(BaseModel):
    items: list[BudgetItemRequest]


class RecurringItemRequest(BaseModel):
    name: str
    amount: float = Field(gt=0)
    category: str = "general"
    item_type: Literal["expense", "income"] = "expense"
    frequency: Literal["weekly", "biweekly", "monthly", "quarterly", "annual"] = "monthly"
    due_day: int | None = Field(default=None, ge=1, le=31)
    is_active: bool = True


class TransactionCreateRequest(BaseModel):
    transaction_date: date
    description: str
    amount: float = Field(gt=0)
    transaction_type: Literal["expense", "income"]
    category: str = "general"
    notes: str = ""


class GmailCandidateReviewRequest(BaseModel):
    transaction_date: date
    description: str = Field(min_length=1, max_length=500)
    # In the currency the movement happened in (USD for a USD purchase).
    amount: float = Field(gt=0, allow_inf_nan=False)
    # "transfer" keeps a movement that is neither income nor spending (a SINPE,
    # a refund, a loan disbursement) as it is when the user fixes another field.
    transaction_type: Literal["expense", "income", "debt_payment", "transfer"]
    category: str = Field(default="general", max_length=100)
    # The user's rate (CRC per 1 USD) when that currency is not the account's base.
    exchange_rate: float | None = Field(default=None, gt=0, le=100000, allow_inf_nan=False)


class OwnTransferConfirmRequest(BaseModel):
    counterpart_id: int = Field(gt=0)
    confirm_owned_accounts: Literal[True]
    unknown_direction: Literal["in", "out"] | None = None


class FinancialAccountIdentityRequest(BaseModel):
    # "pending" = the user does not recognise the account (kept with its review date).
    ownership_status: Literal["own", "not_mine", "pending"]
    display_name: str | None = Field(default=None, max_length=120)


class StatementCutDayRequest(BaseModel):
    """A credit card's cut day: 1–31, or null to clear it (the key is required)."""
    statement_cut_day: int | None = Field(..., ge=1, le=31)


class OwnAccountDeclareRequest(BaseModel):
    institution_code: Literal["bac", "popular", "multimoney", "other"]
    institution_name: str | None = Field(default=None, max_length=60)
    account_last4: str = Field(pattern=r"^\d{4}$")
    currency: Literal["CRC", "USD"] = "CRC"
    display_name: str | None = Field(default=None, max_length=120)


class MovementUpdateRequest(BaseModel):
    transaction_date: date
    description: str
    amount: float = Field(gt=0)
    transaction_type: Literal["expense", "income"]
    category: str = "general"
    notes: str = ""
    # Only manual income and expenses accept another currency.
    currency: Literal["CRC", "USD"] | None = None
    exchange_rate: float | None = Field(default=None, gt=0, le=100000)
    # Only manual expenses carry a "paid with" account (expense_account).
    # The own account or card that paid it (expense_account); not sent = left as it is.
    financial_account_id: int | None = Field(default=None, gt=0)
    # Only a manual expense may wait for the close to be converted (pending_conversion).
    convert_at_close: bool = False


class PendingCloseRequest(BaseModel):
    """The close of one period of dollar expenses (pending_conversion.close_period): one rate for all."""
    period_key: str = Field(min_length=1, max_length=80)
    exchange_rate: float = Field(gt=0, le=100000)


class RetirementUpdateRequest(BaseModel):
    """RT-1 — Retiro: any of these; a field left out keeps its value, a null clears it."""
    rop_balance: float | None = Field(default=None, ge=0, le=1_000_000_000_000, allow_inf_nan=False)
    voluntary_balance: float | None = Field(default=None, ge=0, le=1_000_000_000_000, allow_inf_nan=False)
    birth_year: int | None = Field(default=None, ge=1930, le=2100)
    retire_age: int | None = Field(default=None, ge=50, le=80)
