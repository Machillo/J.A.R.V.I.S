from pydantic import BaseModel


class FinancialGoalRequest(BaseModel):
    name: str
    target_amount: float
    current_amount: float = 0
    target_date: str | None = None
    priority: str = "medium"
    goal_type: str = "general"
    alternative_group: str | None = None
    is_selected: bool = True
    funding_order: int = 100
    depends_on_group: str | None = None


class FinancialGoalUpdateRequest(BaseModel):
    name: str
    target_amount: float
    current_amount: float
    target_date: str | None = None
    priority: str = "medium"
    status: str = "active"
    goal_type: str = "general"
    alternative_group: str | None = None
    is_selected: bool = True
    funding_order: int = 100
    depends_on_group: str | None = None


class GoalContributionRequest(BaseModel):
    amount: float
