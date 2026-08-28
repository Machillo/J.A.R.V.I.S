from pydantic import BaseModel, Field, model_validator


class MoneyEntryRequest(BaseModel):
    amount: float = Field(gt=0)
    description: str = ""
    category: str = "general"
    entry_date: str | None = None


class OvertimeRequest(BaseModel):
    hours: float = Field(gt=0)
    hourly_rate: float = Field(gt=0)
    multiplier: float = Field(default=1.5, gt=0)
    work_date: str | None = None
    notes: str = ""


class DebtRequest(BaseModel):
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


class DebtUpdateRequest(DebtRequest):
    pass


class DebtPaymentRequest(BaseModel):
    amount: float = Field(gt=0)
    payment_date: str | None = None
    notes: str = ""


class StrategySimulationRequest(BaseModel):
    extra_monthly: float = Field(default=0, ge=0)


class VipScenarioRequest(BaseModel):
    monthly_income_change: float = 0
    monthly_expense_change: float = 0
    one_time_extra: float = Field(default=0, ge=0)
