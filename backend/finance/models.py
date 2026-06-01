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