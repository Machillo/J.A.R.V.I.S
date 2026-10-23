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
