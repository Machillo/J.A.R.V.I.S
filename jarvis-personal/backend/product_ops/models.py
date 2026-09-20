from typing import Literal

from pydantic import BaseModel, Field


class ProductEvent(BaseModel):
    event_name: Literal[
        "dashboard_opened", "finance_opened", "debts_opened", "goals_opened",
        "transactions_opened", "strategy_opened", "budget_opened", "calendar_opened",
        "recurring_opened", "reports_opened", "settings_opened", "feedback_submitted",
        "checkout_started", "onboarding_completed", "api_error", "subscription_lifecycle",
    ]
    surface: str = Field(max_length=60)
    success: bool = True
    duration_bucket: Literal["instant", "short", "medium", "long"] | None = None
    app_version: str | None = Field(default=None, max_length=30)


class FeedbackCreate(BaseModel):
    category: Literal["error", "improvement", "payment", "security", "support"]
    subject: str = Field(min_length=3, max_length=140)
    message: str = Field(min_length=5, max_length=4000)
    app_version: str | None = Field(default=None, max_length=30)
    screen: str | None = Field(default=None, max_length=80)
    error_reference: str | None = Field(default=None, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")


class AutomaticIncidentCreate(BaseModel):
    path: str = Field(min_length=1, max_length=160, pattern=r"^/")
    method: str = Field(default="GET", max_length=10, pattern=r"^[A-Za-z]+$")
    status: int = Field(ge=0, le=599)
    request_id: str = Field(min_length=8, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    error_reference: str | None = Field(default=None, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    error_type: str = Field(default="api_error", max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    app_version: str | None = Field(default=None, max_length=30, pattern=r"^[A-Za-z0-9_.+-]+$")
    platform: str | None = Field(default=None, max_length=30, pattern=r"^[A-Za-z0-9_.-]+$")
    screen: str | None = Field(default=None, max_length=80)
    retry_count: int = Field(default=0, ge=0, le=3)


class FeedbackUpdate(BaseModel):
    status: Literal["new", "reviewing", "resolved", "dismissed"]
    owner_notes: str | None = Field(default=None, max_length=2000)


class TestPaymentUpdate(BaseModel):
    action: Literal["confirm", "reject"] = "confirm"


class StoreLifecycleSimulation(BaseModel):
    plan_code: Literal["basic", "vip"]
    provider_event_id: str | None = Field(default=None, min_length=1, max_length=255)
    billing_period: Literal["monthly", "annual"]
    event_type: Literal[
        "trial_started", "purchased", "renewed", "upgrade", "downgrade",
        "cancel_requested", "grace_period", "restored", "expired", "revoked",
    ]
