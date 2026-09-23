"""Manual DINCR store-billing sandbox smoke test.

Run from jarvis-personal with a configured development/test database:

    python -m backend.product_ops.store_billing_smoke

It uses the owner account/workspace supplied through environment variables and
executes the same service used by the owner-only sandbox endpoint. It is
intentionally blocked unless DINCR_BILLING_SMOKE_ALLOW=1 is set.
"""

import os

from backend.auth.current_user import reset_current_user, set_current_user
from backend.product_ops.store_billing import entitlement_state, simulate_lifecycle


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def _expect(expected_plan: str, expected_period: str | None = None, *, canceled: bool | None = None):
    state = entitlement_state()
    assert state["entitlement"] == expected_plan, state
    if expected_period is not None:
        assert state["billing_period"] == expected_period, state
    if canceled is not None:
        assert state["cancel_at_period_end"] is canceled, state
    print(
        f"PASS entitlement={state['entitlement']} status={state['status']} "
        f"period={state['billing_period']} canceled={state['cancel_at_period_end']}"
    )


def main():
    if os.getenv("DINCR_BILLING_SMOKE_ALLOW") != "1":
        raise SystemExit(
            "Refusing to mutate subscription data. Set DINCR_BILLING_SMOKE_ALLOW=1 "
            "only against the intended development/test account."
        )

    account_id = _required("DINCR_BILLING_SMOKE_ACCOUNT_ID")
    workspace_id = _required("DINCR_BILLING_SMOKE_WORKSPACE_ID")
    token = set_current_user(
        {
            "id": int(os.getenv("DINCR_BILLING_SMOKE_LEGACY_USER_ID", "1")),
            "account_id": account_id,
            "workspace_id": workspace_id,
            "workspace_role": "owner",
            "role": "owner",
        }
    )

    try:
        print("1/7 Basic monthly purchase")
        simulate_lifecycle("basic", "monthly", "purchased")
        _expect("basic", "monthly")

        print("2/7 Upgrade to VIP monthly")
        simulate_lifecycle("vip", "monthly", "upgrade")
        _expect("vip", "monthly")

        print("3/7 Cancel VIP; paid access must remain")
        simulate_lifecycle("vip", "monthly", "cancel_requested")
        _expect("vip", "monthly", canceled=True)

        print("4/7 Expire VIP; entitlement must fall to Free")
        simulate_lifecycle("vip", "monthly", "expired")
        _expect("free")

        print("5/7 Basic annual purchase")
        simulate_lifecycle("basic", "annual", "purchased")
        _expect("basic", "annual")

        print("6/7 Restore Basic annual")
        simulate_lifecycle("basic", "annual", "restored")
        _expect("basic", "annual")

        print("7/7 Expire restored subscription; finish on Free")
        simulate_lifecycle("basic", "annual", "expired")
        _expect("free")

        print("DINCR STORE BILLING SMOKE TEST: PASS")
    finally:
        reset_current_user(token)


if __name__ == "__main__":
    main()
