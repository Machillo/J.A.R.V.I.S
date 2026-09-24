# Financial Profiles

Contrasting archetypes for designing and **testing** DINCR logic. Profiles are testing archetypes, not user labels: real users sit between profiles and move among them. DINCR production logic should be driven by normalized state variables (cash flow, reserve coverage, debt burden, etc.), never by assigning a profile name and branching on it.

Each profile gives: signature (in normalized terms), hidden risks, hierarchy position, strategy emphasis, what DINCR must not do, transitions, and edge variants for tests. Concepts referenced here are defined in `financial-framework.md`, `debt-framework.md`, `savings-liquidity.md` and `wealth-investing.md`.

Notation: *E* = essential monthly outflow; *coverage* = liquid reserve / E; *DSR* = debt-service ratio; *CF* = structural monthly cash flow.

## Contents

- P1 Low capital + debt
- P2 Low capital + no debt
- P3 High capital + debt
- P4 High capital + no debt
- P5 Over-indebted
- P6 High income + poor cash flow
- P7 Lower income + strong stability
- P8 Variable / seasonal income
- P9 Strong assets + weak liquidity
- P10 Multiple competing goals
- Reserve-state variants (none / partial / strong)
- Cross-profile transitions
- Contrast pairs (for tests)

---

## P1 — Low capital + debt

**Signature:** coverage < starter; some debt (often revolving); CF slightly positive or near zero; DSR moderate.
**Hidden risks:** any shock goes onto the card; minimum-only payments; interest growth outpaces extra payments.
**Hierarchy:** L2–L3 with L4 pressure.
**Strategy emphasis:** required payments → starter buffer → split between high-cost debt and reserve → payment rollover as debts close. Hybrid payoff often suits (quick wins build adherence).
**Must not:** recommend investing; recommend emptying the tiny buffer for debt; present snowball/avalanche as a moral choice.
**Transitions:** starter reached → weight to debt; high-cost debt gone → complete reserve; CF turns negative → stability logic.
**Edge variants:** debt is only a 0% promo installment (low cost, fixed end); debt is informal family loan with no rate; one debt nearly paid.

## P2 — Low capital + no debt

**Signature:** no debt; coverage low; CF small positive.
**Hidden risks:** "debt-free" feels safe, but no buffer → first shock creates debt; possibly low income with thin margin.
**Hierarchy:** L3.
**Strategy emphasis:** starter buffer → sinking funds for known irregular costs → contextual full reserve → small goals.
**Must not:** label as healthy because debt = 0; push investing before reserve.
**Transitions:** reserve full → goals/investing; shock uses reserve → replenish at starter priority.
**Edge variants:** CF exactly 0; very low income where essentials ≈ income; young user with minimal expenses and family support (unknown support ≠ present support).

## P3 — High capital + debt

**Signature:** significant liquid or investable assets; debt exists (could be cheap mortgage or expensive cards).
**Hidden risks:** carrying high-cost debt while holding idle cash; or the opposite error — liquidating useful reserves/investments to pay cheap debt.
**Hierarchy:** depends on debt cost and liquidity: could be L4 or L6–L7.
**Strategy emphasis:** decompose capital (liquid vs restricted). If high-cost debt and excess liquidity above full reserve → pay the debt from the excess. If low-cost debt → keep paying on schedule; prepay only optionally. Surface the tradeoff with numbers.
**Must not:** treat total capital as available; recommend draining reserve below target; recommend liquidating diversified investments to pay low-cost debt as a default.
**Transitions:** high-cost debt cleared → optimization profile P4.
**Edge variants:** capital mostly illiquid (→ P9); USD mortgage with CRC income; prepayment penalty larger than savings.

## P4 — High capital + no debt

**Signature:** coverage ≥ full target; no debt; CF positive.
**Hidden risks:** excess idle cash (inflation drag), concentration, underinsurance, no estate planning, complacency about variable income.
**Hierarchy:** L6–L7.
**Strategy emphasis:** confirm reserve is contextual (not over-saved), fund goals by horizon, long-term investing concepts, concentration and fee review, professional advice for complex matters.
**Must not:** keep recommending more emergency saving once target is met; generate specific product recommendations via AI.
**Transitions:** job loss or big purchase → re-run from the bottom.
**Edge variants:** very high cash with no stated goals; business owner whose income and capital are the same risk.

## P5 — Over-indebted

**Signature:** essentials + required debt payments ≥ reliable income; DSR critical; delinquencies or borrowing to pay debt.
**Hidden risks:** collateral loss, guarantor exposure, spiraling fees, predatory refinancing, psychological stress causing disengagement.
**Hierarchy:** L1–L2.
**Strategy emphasis:** protect essentials and critical debts (criticality order in `debt-framework.md` §6); stop new borrowing; show which obligations can't be met and consequences; restructuring scenarios; encourage early creditor contact and legitimate counseling; tiny starter buffer to break the borrow loop.
**Must not:** show an avalanche plan with money that doesn't exist; suggest new expensive credit; moralize; show investment content.
**Transitions:** restructuring lowers payments → P1 logic; income rises → re-evaluate.
**Edge variants:** high income but still over-indebted (overlaps P6); all debts current but only via new borrowing; payroll-deducted loans leave little take-home pay.

## P6 — High income + poor cash flow

**Signature:** income in top range for DINCR's users; CF ≤ 0 or erratic; low coverage; lifestyle fixed costs high.
**Hidden risks:** high fixed commitments (housing, vehicles, schools) are hard to reduce; income loss would be catastrophic; perception of wealth delays action.
**Hierarchy:** L2 despite income.
**Strategy emphasis:** fixed-cost analysis, recurring subscriptions and commitments, timing gaps, stop credit-funded lifestyle, build buffer, then treat like P1/P3.
**Must not:** infer health from income; recommend investing because income is high.
**Transitions:** CF positive and buffer built → normal hierarchy.
**Edge variants:** high income with large bonus-dependence (→ P8); negative month caused by one annual expense (temporary, not structural).

## P7 — Lower income + strong stability

**Signature:** modest income; CF positive and consistent; coverage at or near target; little or no costly debt.
**Hidden risks:** limited upside; one large shock (health, job) can still exceed reserves; may under-invest if over-cautious.
**Hierarchy:** L5–L6.
**Strategy emphasis:** preserve what works; sinking funds; goals; small consistent long-term contributions; income-growth opportunities.
**Must not:** treat as fragile because income is low; push risk beyond capacity.
**Transitions:** reserve met → goals/long-term; income rises → avoid lifestyle creep absorbing all of it.
**Edge variants:** stable because of family support (declared vs unknown); low income + zero discretionary spending (sustainability risk).

## P8 — Variable / seasonal income

**Signature:** high income variance across months; possible deficits in low season; self-employed, commission, tourism, agriculture, gig work.
**Hidden risks:** budgeting to average; high-month overspending; misclassifying normal low months as crises; no aguinaldo or employer benefits.
**Hierarchy:** assess over full cycle.
**Strategy emphasis:** baseline-income budgeting; income-smoothing buffer; larger contextual reserve; allocate surplus after it arrives; pre-fund low season.
**Must not:** use a single-month snapshot to classify the user; count expected-but-unreceived income as available.
**Transitions:** stabilizing income → lower coverage target (with hysteresis); new user with < full cycle history → low confidence.
**Edge variants:** one huge month then several zeros; income in USD while expenses in CRC; tax obligations (self-employed) not provisioned.

## P9 — Strong assets + weak liquidity

**Signature:** high net worth; low liquid coverage; wealth in property, business, vehicles, restricted funds or penalized term deposits.
**Hidden risks:** forced sale at bad time; borrowing against assets to cover routine shortfalls; illusion of safety.
**Hierarchy:** L3 (resilience) despite L7-level net worth.
**Strategy emphasis:** build liquid reserve from cash flow; liquidity ladder concepts; avoid new illiquid commitments until liquidity is adequate; surface the net-worth-vs-liquidity gap.
**Must not:** count illiquid assets as reserve; recommend selling assets as routine budgeting.
**Transitions:** liquidity built → P4.
**Edge variants:** large solidarity-association balance only accessible on leaving the employer; term deposit maturing next month (becomes liquid then, not now).

## P10 — Multiple competing goals

**Signature:** several active goals (e.g., emergency reserve, car, travel, education, house deposit, retirement) with required contributions exceeding capacity.
**Hidden risks:** spreading too thin so nothing completes; urgent low-priority goals displacing important ones; short-term goals invested in volatile assets.
**Hierarchy:** L5 (possibly with L3 gap).
**Strategy emphasis:** deterministic ordering (priority → feasibility → deadline), show shortfall and choices (extend, reduce, pause), match instrument risk to horizon, stop contributions to completed goals.
**Must not:** silently underfund all goals; keep funding completed goals; treat reserve as just another goal the user can deprioritize without seeing the risk.
**Transitions:** a goal completes → contributions redistribute explicitly; capacity drops → lower-priority goals pause first.
**Edge variants:** two goals same priority and deadline (tie-breaker); goal with passed deadline; goal target reduced below funded amount.

## Reserve-state variants

Apply across profiles as a second axis:
- **No reserve:** starter buffer is the first discretionary priority after required payments.
- **Partial reserve:** balance continued building vs high-cost debt per cost and income stability.
- **Strong reserve (≥ target):** stop contributions; excess above target can pay high-cost debt or fund goals/investing.

## Cross-profile transitions

Strategy changes when state variables cross thresholds, not when a label changes. Examples:
- P5 → P1: DSR drops below critical after restructuring; required payments now covered → extra-payment strategy becomes available.
- P1 → P2: last debt paid → payment rollover into reserve.
- P2 → P7: reserve at target, CF stable.
- P6 → P3/P4: CF fixed, buffer built, excess capital exists.
- P4 → P2 or P5: job loss, medical event, large new loan.
- P8 in low season looks like P5 month-to-month; at cycle level may be P7.
- P9 → P4: liquidity reaches contextual target.

Use hysteresis so users near thresholds don't flip strategies every period.

## Contrast pairs (for tests)

Pairs that look similar on one metric but require different strategies:
- Same income, different CF: P6 vs P7.
- Same net worth, different liquidity: P4 vs P9.
- Same debt balance, different cost: cheap mortgage (P3 low-cost) vs same amount on cards (P3 high-cost).
- Same monthly deficit, different cause: one-off repair (temporary) vs rent > income (structural).
- Same average income, different variance: salaried vs seasonal (P8).
- Same reserve, different context: single-income self-employed with dependents vs dual-income salaried couple.
- Debt-free but fragile (P2) vs indebted but resilient (P3 with strong reserve and cheap debt).
