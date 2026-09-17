from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AllowedUserRequest(BaseModel):
    email: str
    role: str = "user"
    status: str = "active"

class CheckAccessRequest(BaseModel):
    email: str


class PlanSelectionRequest(BaseModel):
    plan: Literal["free", "basic", "vip"]
    accept_beta_terms: bool = False
    consent_version: str = Field(default="regular-2027-v1", max_length=40)


class LegalAcceptanceRequest(BaseModel):
    accept_terms: bool
    accept_privacy: bool
    terms_version: str = Field(max_length=40)
    privacy_version: str = Field(max_length=40)


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
            raise ValueError("Indicá el salario que realmente te llega al mes.")
        if self.income_type == "hourly" and (self.hourly_rate is None or self.hours_per_day is None):
            raise ValueError("Indicá cuánto te pagan por hora y cuántas horas trabajás normalmente por día.")
        return self


class ProfileSetupRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    usage_goal: Literal["debt", "save", "partner", "life_change", "control", "explore"]
    base_currency: Literal["CRC", "USD", "ARS", "EUR", "MXN", "COP", "GTQ", "PAB"] = "CRC"
    enabled_currencies: list[Literal["CRC", "USD", "ARS", "EUR", "MXN", "COP", "GTQ", "PAB"]] = Field(default_factory=lambda: ["CRC"], min_length=1, max_length=8)
    number_format: Literal["dot_comma", "comma_dot"] = "dot_comma"
    currency_placement: Literal["before", "after"] = "before"

    @model_validator(mode="after")
    def normalize_preferences(self):
        self.display_name = " ".join(self.display_name.split())
        if not self.display_name:
            raise ValueError("Indicá cómo querés que te llamemos.")
        self.enabled_currencies = list(dict.fromkeys([self.base_currency, *self.enabled_currencies]))
        if len(self.enabled_currencies) > 8:
            raise ValueError("Podés activar hasta ocho monedas.")
        return self
