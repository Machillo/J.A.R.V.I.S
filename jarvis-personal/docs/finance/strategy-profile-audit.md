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

- **P1: nothing beyond the emergency fund.**
  - With no debt and savings already at or above the target, Basic still says "use the margin to strengthen your emergency fund" and allocates the whole margin to it.
  - Proposal: once the target is met, move the priority to goals, then to long-term saving/investment ("wealth building"), and keep the emergency line at 0.
  - Impact: medium. The copy and priority change for stable users.
- **P2: savings far above the target never pay expensive debt.**
  - Example: savings of 3 M against a 1.8 M target, with a 52 % APR debt of 1 M. The plan only uses the monthly margin.
  - Proposal: when liquid savings exceed the emergency target by X and a debt's APR is above Y, suggest a one-time payment from the excess, as an optional action that is never automatic.
  - Impact: high. X and Y need a human decision.
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
