from typing import Literal

from pydantic import BaseModel, Field


class ProductEvent(BaseModel):
    event_name: Literal[
        "dashboard_opened", "finance_opened", "debts_opened", "goals_opened",
        "transactions_opened", "strategy_opened", "budget_opened", "calendar_opened",
        "recurring_opened", "reports_opened", "settings_opened", "feedback_submitted",
        "checkout_started", "onboarding_completed", "api_error",
    ]
    surface: str = Field(max_length=60)
    success: bool = True
    duration_bucket: Literal["instant", "short", "medium", "long"] | None = None
    app_version: str | None = Field(default=None, max_length=30)


class FeedbackCreate(BaseModel):
    category: Literal["error", "improvement", "payment", "security", "support"]
    subject: str = Field(min_length=3, max_length=140)
    message: str = Field(min_length=5, max_length=4000)


class FeedbackUpdate(BaseModel):
    status: Literal["new", "reviewing", "resolved", "dismissed"]
    owner_notes: str | None = Field(default=None, max_length=2000)


class TestPaymentUpdate(BaseModel):
    action: Literal["confirm", "reject"] = "confirm"
