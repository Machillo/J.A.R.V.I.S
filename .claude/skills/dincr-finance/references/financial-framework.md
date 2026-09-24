# Financial Framework

The conceptual model DINCR uses to understand a user's financial system: what each dimension means, how the dimensions interact, how the hierarchy is evaluated, how priorities and tradeoffs are resolved, and how a user moves between states.

This file owns **concepts and reasoning**. Mechanics live elsewhere:
debt mechanics → `debt-framework.md`; reserve sizing and cash buckets → `savings-liquidity.md`; investing → `wealth-investing.md`; archetypes → `financial-profiles.md`; production rules → `dincr-strategy-rules.md`.

## Contents

1. Core principles
2. The financial system: dimensions
3. Financial health as a system property
4. The financial hierarchy (levels, entry/exit signals)
5. Prioritization
6. Tradeoffs
7. Temporary vs structural problems
8. Financial state transitions
9. Common reasoning errors

---

## 1. Core principles

- **Evaluate the system, not one metric.** Income, balance, net worth or debt status in isolation mislead. Health emerges from how income, obligations, liquidity, debt and goals interact over time.
- **High income ≠ financial health.** Income is a flow; health depends on what remains after obligations, how reliable it is, and whether it converts into resilience.
- **High capital ≠ liquidity.** Capital may be locked in property, a business, retirement or solidarity-association funds, term deposits, or assets that sell slowly or at a loss.
- **Debt-free ≠ resilient.** A user with no debt, no reserve and unstable income can be one event away from forced borrowing.
- **State-dependence.** The right action depends on the current state. The same surplus should go to different places for different users, and for the same user at different times.
- **Distinguish temporary from structural.** A one-month deficit caused by a known annual expense is not the same problem as a deficit that repeats every month.
- **Uncertainty is information.** Missing or low-confidence data changes what can responsibly be concluded; it should never be silently filled.

## 2. The financial system: dimensions

For each dimension: what it is, what to measure, and the traps.

### 2.1 Income

What: money that reliably arrives to the user's control.

Measure:
- **Net, not gross.** What actually lands after tax, social security (e.g., CCSS worker contributions in Costa Rica) and payroll deductions. Payroll-deducted loan payments or association contributions reduce spendable income before it arrives; they must be modeled as obligations *and* not double-counted.
- **Recurrence and stability:** fixed salary, variable commission, freelance, seasonal, rental, pensions, transfers from family.
- **Concentration:** one employer/client vs several sources.
- **Periodicity:** weekly, biweekly (quincenal is common in Costa Rica), monthly, irregular. Pay-date timing vs obligation-due dates creates intra-month liquidity problems even when the monthly total is fine.
- **Extraordinary income:** aguinaldo, bonuses, tax refunds, sales of assets, gifts, inheritances. These are *not* recurring income and must not inflate the monthly baseline (see `savings-liquidity.md`).

Traps:
- Treating a good month of variable income as the baseline.
- Counting transfers between the user's own accounts as income.
- Counting loan disbursements or credit-card cash advances as income.
- Counting refunds/reversals as income rather than as negative expense.

### 2.2 Expenses

Classify by **flexibility**, not just category:

| Class | Meaning | Examples |
|---|---|---|
| Essential fixed | Must be paid, amount stable | rent/mortgage, utilities base, insurance, school fees |
| Essential variable | Must be paid, amount varies | food, fuel, medicine, transport |
| Contractual debt service | Legally owed on schedule | loan installments, card minimums |
| Committed non-essential | Cancellable with friction | subscriptions, gym, memberships |
| Discretionary | Fully flexible | dining out, entertainment, shopping |
| Irregular/periodic | Predictable but not monthly | marchamo (annual vehicle circulation tax in Costa Rica), insurance premiums, school start, holidays, maintenance |

Traps:
- Irregular expenses averaged away, so the month they hit looks like a crisis.
- Essential vs discretionary misclassified from merchant names alone; classification confidence must be tracked.
- Card purchases counted as expense *and* the card payment counted again as expense (double counting). Choose one accounting basis and apply it consistently.

### 2.3 Cash flow

`net cash flow = reliable net income − (essential + committed + debt service + average irregular + discretionary)` over a defined period.

Distinguish:
- **Structural cash flow:** recurring income minus recurring obligations. Tells whether the model works at all.
- **Observed cash flow:** what actually happened, including one-offs.
- **Minimum-viable cash flow:** income minus essentials and contractual obligations only. Shows how much room exists if discretionary spending were cut; the gap between this and observed cash flow is the *behavioral lever*.
- **Timing cash flow:** whether money is present on the dates obligations are due.

A positive monthly total with negative timing flow still produces late fees and overdrafts.

### 2.4 Liquidity

The ability to meet obligations and absorb shocks **without** selling assets at a loss, paying penalties, or taking new expensive debt.

Liquidity is a spectrum:
1. Immediately available cash (checking, savings, digital wallets such as SINPE Móvil balances).
2. Near-cash (savings accounts with no penalty, money-market funds redeemable in days).
3. Penalized liquidity (term deposits broken early, investments with exit fees or market risk).
4. Illiquid (property, vehicles, business equity, restricted pension/association funds).

Unused credit lines are **not** liquidity for resilience purposes: they are borrowed capacity that can be reduced by the lender and converts a shock into debt. DINCR may show them as "available credit" but must not count them as reserve.

### 2.5 Financial resilience

The ability to absorb a shock (income loss, medical event, repair, family emergency) without falling to a lower hierarchy level.

Resilience depends on:
- liquid reserve relative to essential monthly outflow (coverage in months);
- income stability and diversification;
- fixed-obligation load (high fixed costs reduce the ability to adapt);
- debt-service burden and whether payments can flex;
- insurance coverage and household support network (often unknown → treat as unknown, not as present).

### 2.6 Debt

At the system level, debt matters through four lenses; mechanics are in `debt-framework.md`:
- **Cost:** effective annual cost relative to alternatives.
- **Burden:** share of income consumed by required payments.
- **Rigidity:** penalties, collateral, delinquency consequences.
- **Purpose:** whether it financed an asset, income capacity, consumption, or a past emergency.

Debt is a tool. Its presence is not a verdict.

### 2.7 Goals

A goal has: target amount, target date (or none), priority, flexibility (can the date move? can the amount shrink?), and a funding source.

Horizons:
- **Short (≤ 12 months):** must be held in liquid, low-risk form; functions like a planned expense.
- **Medium (1–5 years):** mostly low/moderate risk; volatility can still damage the outcome.
- **Long (> 5 years):** can tolerate more volatility if capacity allows.

Goals compete with each other and with lower-level needs. A goal is only fundable from genuine surplus or designated extraordinary income, not from money that belongs to operating cash or reserve.

### 2.8 Capital

Total assets minus total liabilities is **net worth**. For decisions, decompose capital by:
- liquidity tier (2.4);
- risk (volatile vs stable);
- restriction (legally or contractually locked);
- purpose (reserve, goal, investable, personal use like a home or car).

Only a subset is **deployable**. See `wealth-investing.md` for what makes capital investable.

## 3. Financial health as a system property

Financial health is not a single score. It is a profile across dimensions. If DINCR computes a composite indicator, it must:
- be decomposable into the component dimensions shown to the user;
- never let strength in one dimension hide a critical weakness in another (use *gating*, not averaging: a critical survival risk caps the overall state regardless of net worth);
- carry a confidence level derived from data completeness.

Examples of why averaging fails:
- High net worth + imminent default on a secured loan → averaging says "healthy"; gating says "survival risk on a critical obligation".
- Excellent savings rate + no reserve because all savings go to an illiquid goal → averaging says "strong saver"; gating says "resilience gap".

## 4. The financial hierarchy

SURVIVAL → STABILITY → RESILIENCE → DEBT OPTIMIZATION → GOALS → WEALTH BUILDING → WEALTH OPTIMIZATION

A user can have activity at several levels, but the **lowest unresolved level constrains** what DINCR should prioritize. Higher-level actions are not forbidden; they are subordinated.

For each level: the question it answers, signals that the user is *in* it, and signals that it is *resolved enough* to shift weight upward. Thresholds are placeholders to be calibrated and approved (see `dincr-strategy-rules.md`).

### L1 — SURVIVAL
Question: Can essential needs and critical obligations be met this period?
In it when: essentials + critical obligations exceed available cash + expected income before due dates; active delinquency on critical debts (secured, housing); utilities/food/medicine at risk.
Priorities: protect housing, food, health, income-generating capacity (e.g., the vehicle used for work), avoid default on secured debt, stop the bleeding. Contact creditors early.
Resolved when: the current period's essentials and critical obligations are covered with a projected non-negative balance.

### L2 — STABILITY
Question: Does the system balance month to month?
In it when: structural cash flow ≤ 0, or recurring overdrafts/late fees, or reliance on new credit to cover routine spending.
Priorities: close the structural gap (reduce fixed costs, restructure payments, increase income), build a small operating buffer, eliminate penalty-generating timing gaps.
Resolved when: structural cash flow positive for several consecutive periods, with no new consumer debt used for recurring expenses.

### L3 — RESILIENCE
Question: Can the user absorb a shock?
In it when: liquid reserve below a contextual starter or full target (see `savings-liquidity.md`).
Priorities: starter buffer first, then build toward the contextual full reserve, in balance with high-cost debt.
Resolved when: reserve meets the contextual target.

### L4 — DEBT OPTIMIZATION
Question: Is the debt structure costing more or risking more than necessary?
In it when: high-cost debt exists, debt-service burden is elevated, or refinancing/restructuring would materially reduce cost or risk.
Priorities: eliminate high-cost debt, reduce burden, simplify structure. Low-cost, manageable debt may coexist with higher levels indefinitely.
Resolved when: no remaining debt is above the "prioritize repayment" cost band and burden is within a healthy range.

### L5 — GOALS
Question: Are defined short/medium-term goals funded on track?
Priorities: fund goals in order of priority × urgency × flexibility; match instrument risk to horizon.

### L6 — WEALTH BUILDING
Question: Is surplus consistently converting into long-term assets?
Priorities: systematic long-term investing/retirement accumulation, diversification, cost awareness.

### L7 — WEALTH OPTIMIZATION
Question: Is an already-healthy system efficient?
Priorities: allocation review, concentration reduction, fee/tax efficiency (with professional advice where regulated), liquidity-return balance, estate/protection considerations.

### Interaction rules
- **Lower-level risk constrains higher-level optimization.** Never optimize portfolio fees while rent is at risk.
- **Levels are not strictly sequential in money flow.** Example: a user may split surplus between starter reserve (L3) and high-cost debt (L4) at the same time; employer-matched retirement contributions (if any) may continue during L3–L4 because the match is an immediate return.
- **Regression is normal.** Job loss can move a user from L6 back to L2. Strategy must re-evaluate every period, not lock a user into a stage.
- **Critical-debt override:** a secured or housing debt in delinquency pulls priority to L1 regardless of net worth.

## 5. Prioritization

When deciding where the next unit of money goes, order considerations roughly as:

1. **Consequence severity** — what happens if this isn't paid/funded? (loss of home, vehicle for work, utility cutoff, legal action) > (late fee) > (goal delay).
2. **Time urgency** — due date proximity.
3. **Irreversibility** — damage that can't be undone (collateral loss, credit-record deterioration) outranks reversible delays.
4. **Cost** — effective rate of debt vs return/value of alternatives.
5. **Resilience impact** — does this action increase or decrease the ability to absorb the next shock?
6. **Behavioral sustainability** — will the plan actually be followed?
7. **Long-term value** — compounding, goal attainment.

This order is a default, not a law. Explanations must reveal which consideration dominated.

## 6. Tradeoffs

Recurring tensions DINCR must make explicit rather than resolve silently:

| Tension | Typical resolution depends on |
|---|---|
| Liquidity vs debt prepayment | reserve adequacy, debt cost, whether prepaid money can be re-borrowed, penalty terms |
| Liquidity vs investing | reserve adequacy, horizon, income stability |
| Debt payoff vs investing | after-tax debt cost vs uncertain expected return, risk capacity, psychological burden |
| Math vs behavior | avalanche vs snowball; a slightly costlier plan that is followed beats an optimal plan abandoned |
| Present vs future goals | urgency, flexibility, consequence of missing each |
| Simplicity vs optimization | complexity cost for the user, data confidence |
| Certainty vs expected value | guaranteed savings from paying debt vs uncertain market returns |

Rule of thumb: when the gap in expected value is small and data confidence is low, prefer the option that **preserves optionality and liquidity**.

## 7. Temporary vs structural problems

| Signal | Temporary | Structural |
|---|---|---|
| Deficit pattern | one or few periods, explained by identifiable events | recurs across periods |
| Cause | irregular expense, medical event, gap between jobs, seasonal dip | fixed costs > reliable income, debt service too high, lifestyle creep |
| Right response | use reserve/buffer, smooth over time, temporary cutbacks | change the structure: costs, income, debt terms |
| Wrong response | restructure life around a one-off | cover repeatedly with reserve or new credit |

Deterministic distinctions need a lookback window, a count of deficit periods, and attribution of large outflows to categories (irregular vs recurring). With too little history, the correct classification is **"undetermined"**, not "temporary".

Seasonal/variable income blurs this: a low month may be structurally normal for a seasonal worker. Evaluate over the full cycle (often 12 months) rather than month by month.

## 8. Financial state transitions

Strategy must respond to changes in the underlying state, not to labels. Key transitions and what should change:

| Transition | Strategy change |
|---|---|
| Deficit → first surplus | Start operating buffer before any goal/investing; avoid over-allocating a first good month |
| Starter buffer reached | Shift weight to high-cost debt while continuing reserve at a lower rate |
| High-cost debt eliminated | Freed payment becomes reserve/goal contribution ("payment rollover") rather than lifestyle absorption |
| Full reserve reached | Stop reserve contributions (avoid over-saving in cash); redirect to goals/investing |
| Goal completed | Stop contributions to that goal; release/redirect its funding explicitly |
| Income drop / job loss | Re-evaluate from L1; pause investing contributions; protect liquidity; consider pausing extra debt payments (keep minimums) |
| Windfall | Evaluate from lowest unresolved level upward (see `savings-liquidity.md`) |
| New debt taken | Recompute burden; check whether it pushes the user down a level |
| Income variability increases | Raise reserve target; switch to baseline-income budgeting |
| Large planned expense approaching | Earmark funds; do not treat them as investable |
| Asset becomes liquid (sale, maturity) | Re-run allocation from the bottom of the hierarchy |

Transitions should use **hysteresis**: require a condition to hold for more than one period (or cross a margin) before changing strategy, so users near a threshold don't oscillate between recommendations each month.

## 9. Common reasoning errors

- Inferring health from income, balance or net worth alone.
- Treating credit limits as savings.
- Treating restricted/illiquid assets as reserve.
- Averaging variable income and budgeting to the average.
- Classifying a one-off as a trend, or a trend as a one-off.
- Recommending investment while high-cost debt or a reserve gap exists, without explaining the tradeoff.
- Recommending liquidation of all reserves to pay cheap debt.
- Presenting estimates as facts.
- Letting a composite score hide a critical risk.
