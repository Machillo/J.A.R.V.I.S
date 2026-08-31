from pydantic import BaseModel


class AllowedUserRequest(BaseModel):
    email: str
    role: str = "user"
    status: str = "active"

class CheckAccessRequest(BaseModel):
    email: str

from typing import Literal
from pydantic import Field, model_validator


class PlanSelectionRequest(BaseModel):
    plan: Literal["free", "basic", "vip"]


class UnifiedOnboardingRequest(BaseModel):
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
        if self.income_type == "hourly" and (self.hourly_rate is None or self.hours_per_day is None):
            raise ValueError("Indicá tarifa por hora y horas por día.")
        return self
