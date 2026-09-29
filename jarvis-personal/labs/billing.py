"""Billing lab: simulated plan states for UX and experiments. Never the entitlement authority.

The real rules live in backend/auth/plan_lifecycle.py and
backend/product_ops/store_state.py (store-verified purchases, courtesies,
scheduled downgrades). Labs does not call Apple or Google (the network guard
blocks them and the environment guard refuses store credentials) and never
changes a real subscription. These fixtures mirror the documented rules so a
screen or an experiment can be exercised in every state; a promoted feature must
be tested against the real modules.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

PLANS = ("free", "basic", "vip")
STATES = ("active", "expired", "cancelled", "pending_downgrade", "courtesy", "verification_failed")


@dataclass(frozen=True)
class SimulatedSubscription:
    plan: str
    state: str
    source: str  # "store" | "courtesy" | "none"
    ends_on: date | None = None
    pending_plan: str | None = None

    def effective_plan(self, today: date) -> str:
        """What the account may use today, per the documented lifecycle rules."""
        if self.plan == "free" or self.state in {"expired", "verification_failed"}:
            return "free"  # DINCR never grants a paid plan nobody bought (or that failed verification)
        if self.ends_on is not None and today >= self.ends_on:
            if self.state == "pending_downgrade" and self.pending_plan == "free":
                return "free"
            return "free" if self.source != "store" or self.state == "cancelled" else self.plan
        return self.plan  # active, courtesy, cancelled-but-paid-through and pending downgrade keep the plan until the end


def catalog(today: date = date(2026, 9, 15)) -> list[SimulatedSubscription]:
    """One subscription per interesting (plan, state) pair."""
    end = date(today.year, today.month, 28)
    return [
        SimulatedSubscription("free", "active", "none"),
        SimulatedSubscription("basic", "active", "store", end),
        SimulatedSubscription("vip", "active", "store", end),
        SimulatedSubscription("vip", "expired", "store", date(today.year, today.month, 1)),
        SimulatedSubscription("vip", "cancelled", "store", end),
        SimulatedSubscription("vip", "pending_downgrade", "courtesy", end, pending_plan="basic"),
        SimulatedSubscription("basic", "courtesy", "courtesy", end),
        SimulatedSubscription("vip", "verification_failed", "store"),
    ]
