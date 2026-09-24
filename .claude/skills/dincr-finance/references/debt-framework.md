# Debt Framework

How DINCR understands, evaluates and prioritizes debt. Debt is a financial tool with costs, risks and uses. It is never encoded as "all debt is bad", and the mathematically cheapest payoff order is never assumed to be the operationally safest.

System-level context (where debt sits in the hierarchy) is in `financial-framework.md`. Reserve sizing is in `savings-liquidity.md`. Invest-vs-prepay from the investing side is in `wealth-investing.md`; this file owns the debt side of that comparison.

## Contents

1. Debt attributes (data model)
2. Effective cost
3. Payments: minimum, contractual, extra
4. Term and amortization
5. Delinquency, penalties and consequences
6. Criticality classes
7. Debt-service burden
8. Liquidity interaction
9. Payoff strategies: avalanche, snowball, hybrid
10. Early repayment
11. Refinancing, consolidation and restructuring
12. Over-indebtedness
13. Debt vs investing
14. Debt vs emergency liquidity
15. Realistic payment capacity
16. Costa Rica considerations
17. Edge-case testing guide

---

## 1. Debt attributes

Each debt should be normalized into at least:

| Field | Notes |
|---|---|
| `debt_id` | internal, non-identifying |
| `type` | credit card, personal loan, payroll-deducted loan, auto, mortgage, student, informal/family, BNPL/installments, overdraft, supplier/business-personal |
| `currency` | CRC, USD, … — currency mismatch with income is a risk factor |
| `balance` | outstanding principal, minor units; with `as_of` date |
| `rate_nominal` | as stated; with rate type (fixed/variable, reference index + spread) |
| `effective_annual_cost` | including mandatory fees/insurance where known |
| `minimum_payment` | for revolving credit |
| `contractual_payment` | for installment debt |
| `payment_frequency`, `next_due_date` | |
| `remaining_term` | installments or months |
| `days_past_due` | delinquency state |
| `penalties` | late fees, default interest, prepayment penalty |
| `collateral` | none, vehicle, property, guarantor (fiador), payroll deduction |
| `is_payroll_deducted` | payment deducted before income arrives |
| `promo_terms` | 0% periods, expiry date, deferred interest |
| `data_confidence` | per field: user-entered, parsed from statement, estimated, unknown |

Missing fields must stay missing. An unknown rate is not 0% and not an assumed average — see §17 and `dincr-strategy-rules.md`.

## 2. Effective cost

Nominal rate understates cost when there are:
- mandatory insurance (e.g., life/unemployment insurance bundled with loans);
- commissions, opening fees, administration fees;
- penalty interest after delinquency;
- currency movement (a USD debt paid from CRC income costs more if the colón depreciates, less if it appreciates — this is uncertain, not a fixed premium);
- deferred-interest promotions that retroactively charge interest if not fully paid by a date.

Cost bands (illustrative; calibrate and approve before production):
- **High cost:** typical of revolving credit cards and many unsecured consumer loans → strong repayment priority after starter buffer.
- **Moderate cost:** some personal and vehicle loans → balance repayment with reserve and goals.
- **Low cost:** below expected long-run returns of conservative alternatives, often secured/mortgage → normally keep paying on schedule; prepayment optional.

Bands should be defined relative to a reference (e.g., current deposit rates or an inflation measure) rather than hard-coded forever, and versioned.

## 3. Payments

- **Minimum payment (revolving):** the least required to avoid delinquency. Paying only the minimum on high-cost revolving debt can make payoff take years and cost multiples of the principal.
- **Contractual payment (installment):** fixed schedule; extra payments may reduce term or installment depending on lender policy.
- **Extra payment:** anything above required. Only extra payments are a strategic choice; required payments are obligations.

Required payments on all debts are part of the stability baseline. Strategy allocates only *extra* money among debts.

## 4. Term and amortization

- Longer term → lower installment, more total interest.
- Early installments are interest-heavy in standard amortization; prepayment early saves more interest.
- A near-finished loan frees cash flow soon; paying it off early may improve cash flow faster than attacking a larger, costlier debt (relevant for hybrid strategy, §9).
- Variable-rate debt carries rate risk; installment may rise.

## 5. Delinquency, penalties and consequences

Delinquency escalates: late fee → penalty interest → reporting to credit bureau / credit-record deterioration → collections → legal action → collateral enforcement / wage garnishment where applicable.

Early delinquency is cheaper to fix than late. A deterministic rule should treat **any** days-past-due on a critical debt as a survival-level signal (see §6).

## 6. Criticality classes

Priority for *required* payments when money is insufficient for all:

| Class | Examples | Why |
|---|---|---|
| Critical-housing | mortgage, rent-like obligations | loss of home |
| Critical-income | loan on a vehicle/tool needed for work | loss of income capacity |
| Secured-other | other collateralized debt | asset loss |
| Legal/tax/alimony | obligations with legal enforcement | legal consequences |
| Guaranteed by third party | loans with a fiador | harm to the guarantor and relationship |
| Unsecured formal | cards, personal loans | credit damage, collections |
| Informal | family/friends | relationship, often flexible (but not always) |

Cost determines *extra*-payment order; criticality determines *required*-payment order under scarcity. These are different questions and must not be merged.

## 7. Debt-service burden

`debt_service_ratio = total required debt payments / reliable net income` (per period).

Include payroll-deducted payments; use net income *before* those deductions for the denominator so the ratio is not understated (or consistently define both — document the choice).

Interpretation bands (illustrative, to calibrate):
- low burden: debt rarely constrains decisions;
- elevated: debt constrains resilience building;
- high: stability at risk; restructuring worth evaluating;
- critical: essentials cannot be covered alongside debt service → over-indebtedness pathway (§12).

A single ratio is insufficient; also check **residual income** after essentials and debt service. A high earner with a 40% ratio may still have ample residual income; a low earner with 25% may not.

## 8. Liquidity interaction

- Paying extra on debt converts liquid money into an illiquid "saving". If a shock follows, the user may re-borrow at higher cost.
- Revolving credit paid down restores available credit, but that credit can be cut by the lender; it is not a reserve.
- Installment prepayments generally cannot be withdrawn.

Therefore: a **starter buffer precedes aggressive extra payments** except where debt cost is extreme *and* consequences of a shock are low. See §14.

## 9. Payoff strategies

Applies only to **extra** money after all required payments.

### Avalanche
Extra money to the highest effective cost first.
Pros: minimizes total interest. Cons: slow first "win" if the costliest debt is large; motivation risk.

### Snowball
Extra money to the smallest balance first.
Pros: fast closures, fewer payments to manage, motivation, frees minimum payments quickly. Cons: can cost more interest.

### Hybrid approaches (DINCR should support explicit, deterministic variants)
- **Cost-band snowball:** avalanche across cost bands, snowball within a band (smallest balance first among similarly priced debts).
- **Quick-win then avalanche:** close any debt payable within N periods of extra money, then avalanche.
- **Cash-flow release:** prioritize debts whose payoff frees the largest required payment relative to remaining balance (`required_payment / balance`), useful when stability (L2) is the binding constraint.
- **Risk-first:** delinquent or critical-consequence debts first, then cost.
- **Promo-expiry aware:** ensure deferred-interest promotions are cleared before expiry if the retroactive charge exceeds the benefit elsewhere.

Tie-breakers must be deterministic (e.g., cost desc → balance asc → `debt_id` asc) so identical inputs always produce identical order.

Explanations should name the strategy, why it was chosen, and the approximate cost difference vs the alternative when known.

## 10. Early repayment

Consider:
- prepayment penalties (compare penalty vs interest saved);
- whether extra payment reduces term or installment (installment reduction improves cash flow; term reduction saves more interest);
- reserve adequacy after prepayment;
- whether money is earmarked for a near-term goal/obligation;
- low-cost debt: prepayment is a legitimate, low-risk "return" equal to the rate, but it competes with liquidity and diversification.

Never recommend draining reserves to prepay low-cost debt.

## 11. Refinancing, consolidation and restructuring

Concepts DINCR can explain (not arrange or promise):
- **Refinancing:** replace debt with lower-cost debt. Evaluate total cost including fees and term extension; a lower installment over a much longer term can cost more in total.
- **Consolidation:** combine debts into one; simpler, possibly cheaper. Risk: freed revolving lines get used again → deeper debt. A deterministic plan should flag that consolidation only helps if revolving usage is controlled.
- **Unsecured → secured conversion:** lower rate but puts an asset (often housing) at risk. Must be surfaced as a risk tradeoff, never as pure savings.
- **Restructuring/readecuación with the lender:** term extension, grace period, rate change; may affect credit record.
- **Balance transfer / promotional rates:** only beneficial if paid off within the promo window or the post-promo rate is still lower.

DINCR can compute scenario comparisons from user-provided terms. It should not recommend specific lenders or products via generative AI.

## 12. Over-indebtedness

Signals (any combination; calibrate thresholds):
- required debt payments + essentials > reliable net income;
- new borrowing used to pay existing debt or routine expenses;
- multiple debts delinquent or near-delinquent;
- revolving balances growing despite payments;
- debt-service ratio in critical band;
- no realistic payoff horizon under current capacity.

Response priorities:
1. Protect essentials and critical obligations (§6).
2. Stop new consumer borrowing.
3. Pay required amounts in criticality order; if impossible, identify which minimums cannot be met and the consequences.
4. Recommend contacting creditors early about restructuring; show scenario math.
5. Suggest looking for qualified, non-predatory debt counseling (general guidance only).
6. Only after stability returns: extra-payment strategy.

Never suggest strategies that hide income from creditors, default intentionally as a tactic, or take high-cost debt to pay debt without surfacing the risk.

## 13. Debt vs investing

Paying debt yields a **certain** return equal to its effective after-tax cost. Investing yields an **uncertain** return. Therefore:
- High-cost debt: repayment almost always dominates investing.
- Low-cost debt: investing may have higher expected value, but with risk; both can coexist.
- Moderate: depends on risk capacity, horizon, liquidity, and behavioral preference.
- Employer/association matches or mandatory contributions are not optional investment choices and follow their own rules.

See `wealth-investing.md` for the investing side.

## 14. Debt vs emergency liquidity

Default sequence (calibrate):
1. Required payments on all debts.
2. Starter buffer.
3. Split extra money between high-cost debt and reserve according to cost and income stability (more to debt when cost is extreme and income is stable; more to reserve when income is volatile).
4. After high-cost debt is gone, complete reserve.
5. Then moderate/low-cost debt vs goals vs investing.

A user with a large reserve and high-cost debt: using the **excess above the contextual full reserve** to pay the debt is usually rational; dipping below the starter buffer usually is not.

## 15. Realistic payment capacity

`capacity = reliable net income − essentials − required debt payments − irregular-expense provision − minimum sustainable discretionary − reserve contribution (if any)`

- Use baseline income for variable earners, not the average.
- Plans that require zero discretionary spending fail; include a minimum sustainable amount.
- Capacity can be negative → no extra-payment plan; route to stability/over-indebtedness logic.
- Recompute capacity every period; a plan is a projection, not a commitment.

## 16. Costa Rica considerations (verify before implementing)

These are context examples; confirm current rules with authoritative sources before encoding product behavior.
- Dual-currency lending (CRC/USD) is common; USD debt with CRC income carries exchange-rate risk.
- A legal cap on credit rates (usury law, set periodically by the central bank) exists; rates still vary widely.
- Payroll-deducted loans from cooperatives and solidarity associations (asociaciones solidaristas) are common; they reduce take-home pay and must be modeled as obligations.
- Guarantor (fiador) arrangements create third-party exposure.
- Marchamo and other annual obligations can trigger card borrowing around year end if not provisioned.

## 17. Edge-case testing guide

Every debt rule must be tested against at least these. Expected behavior is described so tests can assert it.

**Data quality**
- Rate unknown → do not rank by cost; use alternative ordering and mark uncertain; prompt for rate.
- Balance unknown but payment known → include payment in burden; exclude from payoff projection.
- Rate = 0 (genuine promo) vs rate missing → must be distinguishable.
- Stale balance (old `as_of`) → lower confidence; don't project payoff dates as certain.
- Duplicate debt records (same statement parsed twice) → deduplicate before burden calc.
- Payment transaction also recorded as expense → no double counting.

**Structural**
- Single debt → strategy choice irrelevant; don't show avalanche/snowball comparison.
- Two debts equal rate and equal balance → deterministic tie-breaker.
- Highest-rate debt is also smallest → avalanche = snowball; say so.
- Tiny high-rate debt + huge low-rate debt.
- Debt with prepayment penalty greater than interest saved → do not recommend prepayment.
- Promo 0% expiring in N days with deferred interest.
- Variable-rate debt with recent rate increase.
- USD debt, CRC income.
- Payroll-deducted debt with net income already reduced.
- Debt nearly paid (1–2 installments left).
- Negative balance (overpayment/credit) → treat as asset, not debt.

**Liquidity/state**
- No reserve + high-cost debt.
- Large reserve + high-cost debt (excess vs full target).
- Large reserve + only low-cost mortgage → no recommendation to liquidate reserve.
- Negative cash flow + debt → no extra-payment allocation (invariant).
- Extra capacity = exactly 0 → no allocation; boundary.
- Extra capacity smaller than smallest meaningful payment → handle rounding; no fractional-cent allocations.
- Delinquent critical debt while user holds investments → survival override; explain that selling assets may be needed but with tradeoffs.
- Delinquent non-critical debt + current critical debt.

**Over-indebtedness**
- Required payments > income → state flagged; no avalanche plan; criticality ordering shown.
- User takes new loan to pay card → flagged as risk pattern.
- Consolidation that lowers installment but extends term and raises total cost → both numbers shown.

**Behavioral/temporal**
- Strategy stability: a small balance change shouldn't flip the target debt every month (hysteresis or commit-until-paid rule).
- Debt paid off mid-period → freed payment rolls over deterministically.
- Language switch → identical ordering and amounts.
