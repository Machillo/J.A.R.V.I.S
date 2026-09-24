# Savings & Liquidity

How DINCR structures cash, sizes reserves, handles surpluses and deficits, variable income, goal funding and extraordinary income. Emergency reserve requirements are **contextual**, never one universal number.

Dimension definitions (what liquidity and resilience mean) live in `financial-framework.md`. Debt-vs-reserve sequencing from the debt side lives in `debt-framework.md` §14.

## Contents

1. The cash stack (liquidity buckets)
2. Operating cash
3. Starter emergency buffer
4. Full emergency reserve (contextual sizing)
5. Planned short-term spending (sinking funds)
6. Goal reserves
7. Investable capital
8. Surplus and deficit
9. Temporary vs structural deficit handling
10. Variable and seasonal income
11. Savings rate
12. Goal funding
13. Extraordinary income and windfalls
14. Aguinaldo (Costa Rica example)
15. Edge cases

---

## 1. The cash stack

Money is assigned to buckets in a fixed order. Each bucket has a target; overflow goes to the next.

```
1. Operating cash          — this period's obligations until next income
2. Starter emergency buffer — first shock absorber
3. Planned short-term      — known upcoming expenses (≤ 12 months)
4. Full emergency reserve  — contextual months of essentials
5. Goal reserves           — user goals by priority/date
6. Investable capital      — genuinely long-term money
```

The order between (3) and (4), and how extra money splits between (4) and high-cost debt, is a calibrated policy decision; the shown order is a reasonable default. Buckets are *logical*: money may sit in the same account; DINCR tracks assignment, not physical location.

Buckets must never over-allocate: `sum(bucket assignments) ≤ total available liquid money`.

## 2. Operating cash

What must be available to pay essentials, contractual obligations and expected variable spending until the next reliable income date.

- Depends on pay frequency and due-date timing, not only monthly totals.
- A small margin above exact obligations absorbs estimation error.
- Operating cash is **not** savings; showing it as "available to save" is a classic error.

## 3. Starter emergency buffer

A small first reserve that prevents minor shocks (a repair, a medical copay) from becoming new debt.

- Sized as a modest fraction of essential monthly outflow or a fixed minimum floor, whichever is larger — calibrate and approve.
- Built before aggressive extra debt payments or investing.
- For over-indebted users, even a very small buffer matters because it stops the borrow-to-survive loop.

## 4. Full emergency reserve — contextual sizing

Target = `essential_monthly_outflow × coverage_months`, where coverage_months is derived from risk factors. No single number applies to everyone.

Factors that **increase** coverage:
- variable, seasonal, commission or freelance income;
- single income source / single-income household;
- dependents;
- high fixed-cost ratio (little ability to cut);
- specialized job market / long expected job search;
- health risks or incomplete insurance (only if user-declared);
- self-employment (no severance, irregular clients);
- debt with rigid, critical payments;
- currency mismatch (USD obligations, CRC income or vice versa).

Factors that **decrease** coverage:
- stable public-sector or long-tenure employment (judged from data only when known, never inferred from name/employer text alone);
- dual independent incomes;
- low fixed costs;
- access to other reliable liquid resources (declared).

Implementation guidance:
- Use a deterministic scoring table mapping factors → months within a bounded range (e.g., a lower and upper bound approved by humans).
- Base on **essential** outflow, not total spending, so the target is achievable and meaningful.
- Unknown factors → use a conservative default and label it as such; show which inputs would refine it.
- Recompute when income type, dependents or fixed costs change.

Over-saving is also a failure: beyond the target, cash loses value to inflation and opportunity cost. Once the reserve is full, redirect.

## 5. Planned short-term spending (sinking funds)

Known or predictable expenses within ~12 months: marchamo, insurance premiums, school supplies/uniforms, annual subscriptions, maintenance, holidays, medical checkups, appliance replacement.

- Monthly provision = remaining amount / periods until due.
- These are **not** emergencies; paying them from the emergency reserve silently erodes resilience.
- If a sinking fund is underfunded as the date approaches, surface the gap early.

## 6. Goal reserves

Money earmarked for defined user goals. Each goal tracks target, date, priority, flexibility, funded amount and status (`active`, `paused`, `completed`, `cancelled`).

- Short-horizon goals held in liquid, low-risk form.
- **Completed goals stop receiving money.** Overfunding is released to the next priority, with an explicit event.
- Cancelled goals release their funds explicitly (never silently absorbed).

## 7. Investable capital

Money that remains after all lower buckets are at target and that the user will not need for the investment horizon. Details on investing it are in `wealth-investing.md`. This file only decides *whether* money reaches this bucket.

## 8. Surplus and deficit

`period_surplus = reliable income received − all outflows` (with consistent accounting basis).

- **Surplus** → allocate by cash-stack order and hierarchy.
- **Deficit** → drawn from operating cash, then buffer; never produces positive discretionary allocations.
- **Allocatable money** for a period = liquid money − operating cash requirement − already-earmarked funds. If ≤ 0, allocations to goals/investing are zero.

## 9. Temporary vs structural deficit handling

| Type | Detection (deterministic sketch) | Response |
|---|---|---|
| Temporary | deficit in ≤ k of last n periods, explained by irregular/one-off categories | cover from buffer/sinking fund; plan replenishment |
| Seasonal | pattern aligned to known low-income months over a full cycle | pre-fund low months from high months |
| Structural | deficit in ≥ m of last n periods, or recurring outflows > reliable income | change structure; don't mask with reserve or credit |
| Undetermined | insufficient history | say so; recommend conservative behavior; collect data |

Parameters k, m, n are calibrated and versioned.

## 10. Variable and seasonal income

- Budget to a **baseline** (e.g., a low percentile of historical income over a full cycle), not the average.
- Treat income above baseline as surplus to be allocated after the fact, not spent in advance.
- Use an **income-smoothing buffer**: extra months' coverage that pays the user a steady "salary" to themselves.
- Seasonal workers: the relevant window is the full annual cycle; judge health at the cycle level.
- New users with little history: baseline undetermined → conservative assumptions, low confidence.

## 11. Savings rate

`savings_rate = (money moved to reserve + goals + investments + extra debt principal) / reliable net income`

- Whether extra principal counts as saving should be a documented choice; showing both views is useful.
- A high savings rate with no liquid reserve (all into illiquid assets) still leaves resilience gaps.
- A low savings rate can be appropriate during survival/stability repair.
- Never compare a user's savings rate to a universal "should"; compare against their own plan and state.

## 12. Goal funding

Ordering among goals (deterministic): priority → required monthly contribution feasibility → deadline → creation order.

Approaches:
- **Sequential:** fund one goal fully, then the next (clear, faster completion of top goal).
- **Proportional:** split by required monthly contributions (all progress, slower each).
- **Hybrid:** guarantee the most urgent goal's required contribution, split the remainder.

If total required contributions exceed capacity, DINCR should show the shortfall and the options (extend dates, reduce amounts, deprioritize) rather than silently underfund all goals.

## 13. Extraordinary income and windfalls

Bonuses, tax refunds, asset sales, gifts, inheritances, aguinaldo.

- Never add to recurring baseline income.
- Allocate through the hierarchy from the lowest unresolved level upward: overdue critical obligations → operating shortfall → starter buffer → upcoming sinking funds → high-cost debt / full reserve → goals → investable.
- A user-chosen portion for enjoyment is legitimate and improves adherence; the plan should allow an explicit discretionary share, sized in proportion to financial state (smaller when survival/stability is unresolved).
- Large windfalls may justify professional advice (tax, legal, investment), especially inheritances or asset sales.

## 14. Aguinaldo (Costa Rica example)

Costa Rica's aguinaldo is a legally mandated annual extra payment, generally equivalent to about one-twelfth of the salaries earned during the accrual period (roughly December to November), paid in December (commonly within the first ~20 days). It is generally exempt from income tax and worker social-security deductions. Confirm current legal details, including rules for public sector, pensioners and partial-year workers, before encoding product behavior.

Why it matters for DINCR:
- **Predictable windfall:** it can be planned as a known annual inflow for salaried users, but it is not monthly income and must not be spread into the baseline unless the user deliberately smooths it.
- **Year-end pressure:** December–January concentrates holiday spending, school-start costs in early year, and marchamo (typically due by year end). Aguinaldo is often fully consumed or used to cover card debt accumulated during the year.
- **Strategy by state (illustrative):**
  - Survival/stability: overdue obligations, then marchamo/school sinking funds, then starter buffer.
  - High-cost debt present: after sinking-fund gaps and starter buffer, a large share to highest-priority debt.
  - Reserve incomplete, no costly debt: reserve completion.
  - Stable: goals and long-term investing, with an explicit discretionary share.
- **Estimating it:** DINCR can estimate from observed salary history, but the estimate must be labeled as such (partial-year employment, variable pay and salary changes affect it). Variable-income and self-employed users typically do not receive it.

## 15. Edge cases

- Liquid balance below operating requirement → allocatable money = 0; show shortfall.
- Reserve exactly at target → no further contributions; no oscillation from tiny fluctuations (hysteresis).
- Reserve used for an emergency → replenishment plan re-enters at starter-buffer priority.
- Sinking fund due date passed without payment detected → mark uncertain; do not assume paid.
- Goal completed mid-period → stop contributions; release overflow.
- Goal target lowered below funded amount → release excess explicitly.
- Multiple currencies → buckets per currency or converted with a dated rate; label conversions as estimates.
- Transfers between own accounts → not income, not expense.
- Refunds → reduce expenses, not income.
- Windfall arrives while in deficit → cover deficit first.
- First month of data → targets are provisional; confidence low.
- Seasonal worker in high season → surplus should pre-fund low season before goals.
- Aguinaldo estimated but not yet received → do not allocate as available money until it arrives.
