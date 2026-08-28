from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ProfileStatusRequest(BaseModel):
    status: str


class ProfileRoleRequest(BaseModel):
    role: str


class PlanSelectionRequest(BaseModel):
    plan: Literal["free", "basic", "vip"]


class OnboardingDebtRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    remaining_amount: float = Field(gt=0)
    total_amount: float | None = Field(default=None, gt=0)
    monthly_payment: float | None = Field(default=None, ge=0)
    interest_rate: float | None = Field(default=None, ge=0)
    payment_day: int | None = Field(default=None, ge=1, le=31)

    @model_validator(mode="after")
    def validate_amounts(self):
        if self.total_amount is not None and self.remaining_amount > self.total_amount:
            raise ValueError("El saldo pendiente no puede superar el monto total.")
        return self


class OnboardingGoalRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_amount: float = Field(gt=0)
    current_amount: float = Field(default=0, ge=0)
    target_date: str | None = None
    priority: Literal["low", "medium", "high", "critical"] = "medium"


class OnboardingRequest(BaseModel):
    income_type: Literal["fixed", "hourly"]
    work_days_per_week: int = Field(ge=1, le=7)
    pay_frequency: Literal["weekly", "biweekly", "monthly"]
    payday_note: str | None = Field(default=None, max_length=80)
    fixed_monthly_salary: float | None = Field(default=None, gt=0)
    hourly_rate: float | None = Field(default=None, gt=0)
    hours_per_day: float | None = Field(default=None, gt=0, le=24)

    essential_monthly_expenses: float | None = Field(default=None, ge=0)
    liquid_savings: float | None = Field(default=None, ge=0)
    emergency_fund_target: float | None = Field(default=None, ge=0)

    has_debts: bool = False
    debts: list[OnboardingDebtRequest] = Field(default_factory=list, max_length=50)

    has_goals: bool = False
    goals: list[OnboardingGoalRequest] = Field(default_factory=list, max_length=25)

    strategy_preference: Literal["debt", "emergency", "goals", "balanced"] | None = None
    discretionary_monthly_minimum: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_income_and_lists(self):
        if self.income_type == "fixed" and self.fixed_monthly_salary is None:
            raise ValueError("Indicá tu salario mensual.")
        if self.income_type == "hourly":
            if self.hourly_rate is None:
                raise ValueError("Indicá cuánto ganás por hora.")
            if self.hours_per_day is None:
                raise ValueError("Indicá cuántas horas trabajás por día.")
        if not self.has_debts and self.debts:
            raise ValueError("No enviés deudas si indicás que no tenés deudas.")
        if not self.has_goals and self.goals:
            raise ValueError("No enviés metas si indicás que no tenés metas activas.")
        return self

class FinancialSituationUpdateRequest(BaseModel):
    income_type: Literal["fixed", "hourly"]
    work_days_per_week: int = Field(ge=1, le=7)
    pay_frequency: Literal["weekly", "biweekly", "monthly"]
    payday_note: str | None = Field(default=None, max_length=80)
    fixed_monthly_salary: float | None = Field(default=None, gt=0)
    hourly_rate: float | None = Field(default=None, gt=0)
    hours_per_day: float | None = Field(default=None, gt=0, le=24)
    essential_monthly_expenses: float | None = Field(default=None, ge=0)
    liquid_savings: float | None = Field(default=None, ge=0)
    emergency_fund_target: float | None = Field(default=None, ge=0)
    strategy_preference: Literal["debt", "emergency", "goals", "balanced"] | None = None
    discretionary_monthly_minimum: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_income(self):
        if self.income_type == "fixed" and self.fixed_monthly_salary is None:
            raise ValueError("Indicá tu salario mensual.")
        if self.income_type == "hourly":
            if self.hourly_rate is None:
                raise ValueError("Indicá cuánto ganás por hora.")
            if self.hours_per_day is None:
                raise ValueError("Indicá cuántas horas trabajás por día.")
        return self
