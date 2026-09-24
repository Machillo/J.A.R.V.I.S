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

## Proposals: HUMAN GATE (financial rules, not changed)

They are encoded as `xfail(strict=True)` tests. They start failing ("XPASS") if someone changes the rule, which forces a conscious update.

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
- **P2: savings far above the target never pay expensive debt. INFRASTRUCTURE IMPLEMENTED, DISABLED (HUMAN GATE).**
  - `excess_savings_opportunity` computes `excess_savings = max(liquid_savings − emergency_fund_target − Σ goals.current_amount, 0)`. Money already set aside for goals is never excess.
  - It is offered only when the month's margin is positive (not `tight`, `critical` or `needs_income`). The copy warns about early-payment fees and that a loan prepayment cannot be undone. It considers only active debts with a **known** APR ≥ `HIGH_COST_DEBT_APR_THRESHOLD`.
  - It picks the debt with the existing deterministic debt score (known rate, highest rate, earliest due day, smaller balance, oldest record) and proposes `min(excess_savings, remaining_amount)`.
  - The result goes to a separate `optional_actions` list with `source="excess_savings"`, `optional=True`, `executes=False`. The monthly `allocations` never change.
  - Savings after the suggestion are always ≥ the target, and an unknown target never produces an excess.
  - DINCR never moves money, edits debts or registers payments from this rule.

### P2 threshold decision (human approval: Kenneth)

`HIGH_COST_DEBT_APR_THRESHOLD` is `None` in `backend/user_product/strategy_engine.py`, so P2 never fires in production. Its test (`test_p2_is_active_for_expensive_debt_with_excess_savings_in_production`) is strict-xfail until the decision is made.

What already exists in the code:

| Value | Where | What it decides today |
|---|---|---|
| APR ≥ 10 % ("deuda cara") | `advisor/core.py` (Owner), `ai/strategy_dashboard.py` (VIP strategy dashboard), `goals/strategy.py` | blocks investing and goal funding while such a debt exists |
| APR ≥ 20 % | `finance/service.py` (Owner) | "high interest" review recommendation |
| APR ≥ 25 % | `ai/strategy_dashboard.py` | ordering bucket for payoff priority |

None of these values was approved for **using existing savings**, which is a different, liquidity-reducing decision.

Decision needed:
1. the APR value for "very expensive debt" in this rule (reuse the 10 % "deuda cara" classification, or pick a stricter one such as 20–25 %);
2. inclusive at the value (as implemented) or not;
3. whether the rule should also require fixed/stable income or an extra buffer for variable income, and whether card and installment debt should be treated differently. Today it requires a positive monthly margin and excludes goal savings;
4. the UI placement of the optional suggestion. The Basic/VIP screens do not render `optional_actions` yet, so a screen change is needed when the rule is activated.

The DINCR Finance review suggests defining the threshold relative to a reference (deposit rates or inflation), versioning it, and checking CRC vs USD debts separately. 10 % would also catch moderate-cost vehicle and personal loans; 20–25 % matches the "high cost" band (cards, unsecured consumer loans).

### P1/P2 follow-ups (human decisions, not implemented)
- **Goal funding policy.** Goals are funded fully one after another. Alternative: pay each dated goal its required monthly amount first (`_goal_monthly_need` exists), then split the rest.
- **VIP allocations.** VIP inherits the Basic priority, but its weights still send the no-debt share to `flex` and have no `wealth_building` line.
- **Hysteresis and reason codes** for the switch at `savings >= target`.
- **Planned short-term expenses** (marchamo, school, holidays) are not modeled, so they can land in `wealth_building`.

Once decided, set the constant, flip the xfail test to a normal test, add −ε/=/+ε boundary tests at the approved value, and render the suggestion.
- **P3: the engine has no input for illiquid assets or income volatility.**
  - For "high net worth, illiquid" and "variable income", the engine only sees liquid savings and an average income.
  - Proposal: a variability buffer for hourly/variable income (a larger emergency target, in months), plus an asset/liquidity input.
  - Impact: medium. This needs product design, so it is post-launch.
- **P4: Basic can emit two `emergency` lines** when there is no debt: "Reserva de emergencia" plus "Ahorro / fondo de emergencia". This is cosmetic, but a UI that keys by bucket would merge or duplicate them. It could be merged into one line.
- **P5: in a critical month, the paycheck plan lists essentials plus minimums above the paycheck.** It just reflects the deficit, and `unassigned` stays at 0. The copy could say "deficit this period" explicitly.

## Sanitized aggregate metrics (concept, not implemented)

Goal: improve these rules with evidence, never with raw personal data. The flow follows `CLAUDE.md`: sanitized/aggregated data → hypothesis → synthetic test → deterministic proposal → human review → versioned rule.

1. **Emission.** When a strategy is computed, record only an **anonymous tuple**: `engine_version`, `plan` (basic/vip), `status`, `priority`, and banded ratios. The bands are commitment ratio (0–40/40–60/60–80/80–100/>100 %), emergency coverage (0/<1/1–3/3–6/>6 months), APR band of the target debt, number of active debts (0/1/2–3/4+) and income type (fixed/hourly).
   - Never record amounts, names, account/workspace ids or free text.
2. **Storage.** A server-only table `strategy_metrics_daily(date, engine_version, plan, status, priority, bands…, count)`. It is incremented with `ON CONFLICT DO UPDATE` and has no per-user rows.
   - Keep k-anonymity: only publish cells with count ≥ 20.
   - RLS enabled, and grants revoked from `anon`/`authenticated`.
3. **Review.** An Owner-only report shows transitions, such as the share of "tight" users who reach "healthy" within 3 months (from `financial_health_snapshots` aggregates).
   - Hypotheses become new synthetic profiles in this battery before any rule changes.
4. **Guardrails.**
   - AI may read only the aggregate report to propose hypotheses.
   - It never writes rules, never sees rows, and never activates anything.
   - Rule changes ship as a versioned engine (`engine_version`) after human approval.

Implementing (1)–(2) needs a migration and a privacy-policy check, so it is a human gate and post-launch.
