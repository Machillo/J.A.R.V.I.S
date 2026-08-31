from typing import Literal
from pydantic import BaseModel, Field, model_validator


class IncomeCreateRequest(BaseModel):
    amount: float = Field(gt=0)
    description: str = ""
    category: str = "salario"
    entry_date: str | None = None


class ExpenseCreateRequest(BaseModel):
    amount: float = Field(gt=0)
    description: str = ""
    category: str = "general"
    entry_date: str | None = None


class OvertimeCreateRequest(BaseModel):
    hours: float = Field(gt=0)
    hourly_rate: float = Field(gt=0)
    multiplier: float = Field(default=1.5, gt=0)
    work_date: str | None = None
    notes: str = ""


class UserDebtCreateRequest(BaseModel):
    name: str
    total_amount: float | None = Field(default=None, ge=0)
    remaining_amount: float = Field(ge=0)
    monthly_payment: float | None = Field(default=None, ge=0)
    interest_rate: float | None = Field(default=None, ge=0)
    payment_day: int | None = Field(default=None, ge=1, le=31)


class DebtPaymentRequest(BaseModel):
    amount: float = Field(gt=0)


class BasicSimulationRequest(BaseModel):
    extra_monthly: float = Field(default=0, ge=0)


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
            raise ValueError("Indicá tu salario mensual.")
        if self.income_type == "hourly" and (self.hourly_rate is None or self.hours_per_day is None):
            raise ValueError("Indicá tarifa por hora y horas por día.")
        return self
