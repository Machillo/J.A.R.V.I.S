from pydantic import BaseModel


class FinancialGoalRequest(BaseModel):
    name: str
    target_amount: float
    current_amount: float = 0
    target_date: str | None = None
    priority: str = "medium"


class FinancialGoalUpdateRequest(BaseModel):
    name: str
    target_amount: float
    current_amount: float
    target_date: str | None = None
    priority: str = "medium"
    status: str = "active"


class GoalContributionRequest(BaseModel):
    amount: float