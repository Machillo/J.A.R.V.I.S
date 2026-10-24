from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator

# Exact-amount distribution: a reasonable ceiling (₡1.000 millones) against a mistyped amount.
EXACT_DISTRIBUTION_MAX = Decimal("1000000000")


class ExactDistributionRequest(BaseModel):
    """The money the Owner confirms having, to distribute with the current strategy (planning only)."""
    amount: Decimal = Field(gt=0, le=EXACT_DISTRIBUTION_MAX, max_digits=12, decimal_places=2)
    currency: str = "CRC"

    @field_validator("currency")
    @classmethod
    def _colones_only(cls, value: str) -> str:
        # The Owner's strategy works in colones; another currency is never added or converted silently.
        if str(value).strip().upper() != "CRC":
            raise ValueError("Por ahora la distribución exacta es solo en colones (CRC).")
        return "CRC"


class ExpectedDistributionItem(BaseModel):
    key: str = Field(min_length=1, max_length=40)
    amount: Decimal = Field(ge=0, le=EXACT_DISTRIBUTION_MAX, max_digits=12, decimal_places=2)


class ExactDistributionConfirmRequest(ExactDistributionRequest):
    """CONFIRMAR: the Owner declares he carried out the distribution he reviewed.

    `confirmation_key` identifies this confirmation (one per reviewed distribution): repeating it
    never applies it twice. `expected_items` and `plan_fingerprint` are the split and the plan the
    Owner saw; the server recomputes both and records nothing when either differs."""
    confirmation_key: str = Field(pattern=r"^[A-Za-z0-9_-]{8,80}$")
    expected_items: list[ExpectedDistributionItem] = Field(min_length=1, max_length=12)
    # The `confirmation_plan.fingerprint` the Owner reviewed (which debt and goal get what).
    plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("expected_items")
    @classmethod
    def _one_amount_per_destination(cls, items: list[ExpectedDistributionItem]) -> list[ExpectedDistributionItem]:
        if len({item.key for item in items}) != len(items):
            raise ValueError("Cada destino va una sola vez.")
        return items


class JarvisChatRequest(BaseModel):
    message: str


class JarvisChatResponse(BaseModel):
    message: str
    intent: str | None = None
    action_type: str | None = None
    status: str = "OK"
    pending: bool = False
    data: dict | None = None


class SportsFootballPreferences(BaseModel):
    teams: list[str] | None = None
    competitions: list[str] | None = None


class SportsPreferencesRequest(BaseModel):
    f1: bool | None = None
    ufc: bool | None = None
    football: SportsFootballPreferences | None = None
    notification_style: str | None = None


class BrowserSubscriptionRequest(BaseModel):
    endpoint: str | None = None
    payload: dict[str, Any] | None = None
    permission: str | None = None

class MemoryItemRequest(BaseModel):
    content: str
    category: str | None = None
    title: str | None = None
    importance: int = 3


class ProfilePreferencesRequest(BaseModel):
    display_name: str | None = None
    response_style: str | None = None
    notification_style: str | None = None
    voice_gender: str | None = None
    voice_speed: str | None = None
    voice_tone: str | None = None
    timezone: str | None = None
    language: str | None = None
    avatar_data_url: str | None = None
