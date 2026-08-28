from pydantic import BaseModel, Field


class FinancialGoalRequest(BaseModel):
    name: str
    target_amount: float = Field(gt=0)
    current_amount: float = Field(default=0, ge=0)
    target_date: str | None = None
    priority: str = "medium"


class FinancialGoalUpdateRequest(FinancialGoalRequest):
    status: str = "active"
