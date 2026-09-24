# Users strategy engine — synthetic profile audit

Scope: `backend/user_product/strategy_engine.py`, the deterministic engine behind `/user-product/finance/strategy-basic` (Basic) and `/strategy-vip` (VIP): priority, allocations, paycheck plan, scenarios and insights.

Not covered here: VIP also calls other endpoints backed by the JARVIS-derived engines (`/vip/strategy-dashboard`, `/vip/debt-advisory`, `/vip/debt-strategies`, `/vip/salvavidas`). Those read the database, and they are the next candidates for the same treatment. Owner's `advisor/core.py` is internal.

Battery: `backend/tests/test_strategy_profiles.py`. It covers 16 fictitious profiles (CRC), with no personal data:

| Profile | Basic status / priority |
|---|---|
| over-indebted | critical / stabilize |
| manageable debt | healthy / debt |
| no debt | healthy / emergency |
| no emergency fund | healthy / debt (starter reserve ≤ 20 % of margin) |
| partial / healthy emergency fund | healthy / emergency |
| good saver | healthy / emergency |
| variable (hourly) income | healthy / debt |
| low income, high essentials | critical / stabilize |
| high income, poor liquidity | healthy / debt |
| high net worth, illiquid | healthy / debt |
| expensive debt + savings | healthy / debt |
| multiple debts | healthy / debt (highest known APR, then earliest due day) |
| goals competing with debt | healthy / debt; VIP gives the critical dated goal its share |
| stable | healthy / emergency |
| wealth-building ready | healthy / emergency (see P1) |

Checked for every profile:
- **No impossible allocations:** no negative or sub-cent amounts, and allocations never exceed the strategic margin (+ extra).
- **VIP completeness and caps:** VIP assigns the whole margin, including flex; an emergency line never exceeds the remaining gap; debt lines point only to active debts.
- **Projections:** an extra payment never slows a payoff.
- **Paycheck plan:** never negative.
- **Language:** ES and EN give identical numbers and buckets.

Also tested:
- **Threshold crossing:** a margin of −0.01 is critical, 0 is tight, and +0.01 is healthy.
- **Missing data:** it is warned about, never invented.
- **Payoff projection:** when the payment is at or below the interest, there is no payoff estimate.
- **Hourly income estimate:** 52/12 weeks per month.
- **Scenarios:** they are pure (they never mutate the snapshot).
- **Input order:** shuffling debts or goals never changes the result.

## Fixed (no change in production behavior)

1. **Exact ties depended on input order.** Two debts with the same APR, due day and balance were chosen by list position.
   - The engine now breaks ties by the oldest record (lowest id). That is exactly what production already did, because the snapshot query uses `ORDER BY id`.
   - Goals got the same tie-break.
2. **VIP could target a paid-off debt.** `build_vip_strategy` did not filter `remaining_amount > 0`, unlike Basic. The production snapshot already filters these debts, so no user was affected, but the engine is now consistent on its own.

## Proposals (financial rules)

P1 and P2 were approved and are implemented, covered by normal tests in `backend/tests/test_strategy_profiles.py`. P3–P5 remain documented proposals that need human approval.

- **P1: nothing beyond the emergency fund. IMPLEMENTED.**
  - Rule, applied only when there is no active debt and the emergency target is known (> 0):
    1. the monthly margin fills the emergency fund only up to its real gap (`target − liquid_savings`, net of the starter reserve);
    2. the remainder goes to active goals, ordered by priority, then nearest date, then oldest record, each capped at its remaining gap;
    3. whatever is left becomes a `wealth_building` line.
  - Priority:
    - `emergency` while `liquid_savings < target`;
    - `goals` once the fund is complete and an active goal remains;
    - `wealth_building` otherwise.
  - The wealth-building text names no product, instrument or return.
  - An unknown target (None/0) keeps the previous behavior: DINCR cannot know the fund is complete, and unknown is not zero.
  - Unknown essential expenses never produce a `wealth_building` line. The remainder stays as "margin to confirm" (`flex`), and with no goals the priority is `complete_profile`.
  - Debt logic is untouched: with any active debt the priority stays `debt`.
  - VIP inherits the priority from Basic, and its emergency line was already capped at the gap.
  - Pinned profiles that changed on purpose: `healthy_emergency_fund` and `wealth_building_ready` (→ `wealth_building`), `good_saver` and `stable` (→ `goals`). No other profile changed.
- **P2: excess savings vs. very expensive debt. IMPLEMENTED AND ACTIVE (threshold approved).**
  - `excess_savings_opportunity` computes `excess_savings = max(liquid_savings − emergency_fund_target − Σ goals.current_amount, 0)`. It needs a **known** emergency target, and money already set aside for goals is never excess.
  - Eligible debts: active, with a **known** nominal APR ≥ `HIGH_COST_DEBT_APR_THRESHOLD`. A debt with unknown APR is never eligible; the snapshot also turns a stored 0 into unknown.
  - The debt is picked with the existing deterministic debt score (known rate, highest rate, earliest due day, smaller balance, oldest record). The suggested amount is `min(excess_savings, remaining_amount)`.
  - It is offered only when the month's margin is positive (not `tight`, `critical` or `needs_income`).
  - It lives in a separate `optional_actions` list: `source="excess_savings"`, `optional=True`, `executes=False`. The monthly `allocations` and `strategic_margin` are identical with or without it, and a test covers every profile.
  - DINCR never moves money, records payments or edits debts, accounts, savings or movements from this rule. The only consumer is an informative card in Basic and VIP, with no action button.
  - The copy tells the user to confirm the excess isn't needed for upcoming expenses DINCR doesn't know about, to check early-payment fees, and that a prepayment cannot be undone.

### P2 threshold decision (approved for v1 by Kenneth)

`HIGH_COST_DEBT_APR_THRESHOLD = 20.0`, **inclusive** (`APR >= 20.0`). Boundaries are tested: 19.99 % not eligible; 20.00 % and 20.01 % eligible.

For v1:
- the same nominal threshold applies to CRC and USD debts;
- it is not relative to inflation, deposit rates or any external variable;
- a positive monthly margin and a known emergency target are required;
- the emergency fund and goal savings are never touched.

For reference, other values in the code keep their own meaning:

| Value | Where | What it decides |
|---|---|---|
| 10 % ("deuda cara") | advisor/core (Owner), ai/strategy_dashboard (VIP dashboard), goals/strategy | blocks investing and goal funding |
| 25 % | ai/strategy_dashboard | payoff ordering |

**Known limitation.** DINCR does not model planned short-term expenses (marchamo, school costs, holidays…). P2 can only protect the reserves DINCR knows about: the emergency target and goal savings. It does **not** claim the whole excess is disposable, so the UI asks the user to confirm they don't need it for upcoming expenses before paying.

**Where it shows.** The Basic strategy screen shows it in both its Basic and VIP branches. VIP users normally see the VIP strategy dashboard, which is a different engine. There, `VipStrategy` fetches `/user-product/finance/strategy-vip` only to render the same optional card above the dashboard, without touching that engine.

### P1/P2 follow-ups (human decisions, not implemented)
- **Goal funding policy.** Goals are funded fully one after another. Alternative: pay each dated goal its required monthly amount first (`_goal_monthly_need` exists), then split the rest.
- **VIP allocations.** VIP inherits the Basic priority, but its weights still send the no-debt share to `flex` and have no `wealth_building` line.
- **Hysteresis and reason codes** for the switch at `savings >= target`.
- **Planned short-term expenses** (marchamo, school, holidays) are not modeled, so they can land in `wealth_building`, and P2 cannot exclude them from the excess. This is documented, and the P2 UI asks the user to confirm. No new reserve is invented.
