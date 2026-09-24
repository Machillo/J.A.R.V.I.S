# DINCR Strategy Rules

How broad financial knowledge becomes **deterministic, testable, explainable, versioned** DINCR production behavior — and how rules may improve over time without compromising privacy.

OFFLINE ANALYSIS PROPOSES. DINCR EXECUTES DETERMINISTICALLY. HUMANS APPROVE FINANCIAL RULE CHANGES.

DINCR has no generative-AI runtime: no model is called while computing, parsing or presenting a user's finances. AI may only be used offline, by developers, on sanitized material (e.g., Parser Discovery).

Generative AI must never be required to reconstruct, compute or justify a production financial decision. Every decision must be reproducible from normalized inputs + rule version alone.

## Contents

1. Decision pipeline
2. Normalized data model
3. Rule specification template (required for every rule)
4. Worked rule examples
5. Missing-data policy
6. Thresholds, boundaries and hysteresis
7. Invariants
8. Explainability contract
9. Profile-matrix testing
10. Test types
11. Rule lifecycle and versioning
12. Financial learning loop (privacy-gated)
13. Rule review checklist

---

## 1. Decision pipeline

```
raw sources (statements, emails, manual entry)
 → parsing (deterministic parsers; offline tooling may help design parsers, never runs in production)
 → normalization (canonical money, dates, categories, dedup, transfer detection)
 → state computation (cash flow, coverage, DSR, capacity, allocatable money…)
 → rule evaluation (versioned deterministic rules → priority + allocations + reason codes)
 → explanation assembly (reason codes + drivers → templates)
 → presentation (localization and formatting from deterministic templates)
```

Layer boundaries:
- Financial numbers are produced only by the normalization, state and rule layers.
- Localization operates on already-decided outputs; it cannot change amounts, orderings or priorities.
- Every output stores: `rule_set_version`, input snapshot hash, reason codes, and data-confidence summary.

## 2. Normalized data model

Principles:
- **Money:** integer minor units + ISO currency code. No floats in persistence or calculations. Define rounding mode (e.g., banker's or half-up) and where it is applied (only at final allocation step), and allocate remainders deterministically.
- **Currency conversion:** explicit, dated rate with source; converted values carry `estimated=true`.
- **Dates:** timezone-normalized (Costa Rica, UTC−6, no DST) with period boundaries defined once.
- **Provenance & confidence** per field: `user_entered | parsed | derived | estimated | missing`.
- **Deduplication:** stable fingerprint (amount, date window, account, normalized reference) before any aggregation.
- **Transfers:** internal transfers and card payments recognized so they are neither income nor double-counted expense.
- **Categories:** stable internal category codes, language-independent; display names are localized separately.

Core normalized state (illustrative names):

| Variable | Definition |
|---|---|
| `reliable_income_period` | baseline net income (salaried: recent recurring; variable: low-percentile over cycle) |
| `essential_outflow_period` (E) | essential fixed + essential variable + irregular provision |
| `required_debt_payments_period` | all contractual/minimum payments |
| `structural_cf` | reliable income − recurring outflows |
| `liquid_balance` | sum of tier-1/tier-2 liquid accounts |
| `operating_requirement` | obligations until next income + margin |
| `earmarked_total` | sinking funds + goal reserves already assigned |
| `allocatable` | `max(0, liquid_balance − operating_requirement − earmarked_total)` |
| `reserve_coverage` | reserve bucket / E |
| `reserve_target_months` | from contextual scoring table |
| `dsr` | required_debt_payments / reliable_income |
| `high_cost_debt_exists` | any debt in high-cost band with known rate |
| `critical_delinquency` | any critical-class debt with days_past_due > 0 |
| `income_variability` | coefficient of variation or percentile spread over window |
| `history_months` | months of usable data |
| `data_confidence` | aggregate per input group |

## 3. Rule specification template

Every proposed financial rule must be written in this form before implementation. Missing sections block approval.

```
RULE ID / NAME / VERSION:
PURPOSE: one sentence; hierarchy level it serves.
FINANCIAL RATIONALE: why this is sound; which reference concept it implements.

1. NORMALIZED INPUTS: variables used, units, source, required vs optional.
2. DETERMINISTIC CONDITIONS: exact predicates, evaluation order, inclusive/exclusive bounds.
3. DETERMINISTIC OUTPUT: priority code, allocations (minor units), flags, reason codes.
4. EXPLANATION: reason code(s) + driver values + "what could change this".
5. MISSING-DATA BEHAVIOR: per input, what happens if missing/low confidence (see §5).
6. BOUNDARIES / THRESHOLDS: parameter names, values, version, justification, hysteresis.
7. EDGE CASES: enumerated with expected outputs.
8. TESTS: unit, boundary, property/invariant, profile-matrix rows, metamorphic.

INTERACTIONS: rules it precedes/overrides/depends on; conflict resolution.
APPROVAL: reviewer, date, decision, evidence summary (privacy-safe).
```

## 4. Worked rule examples

These illustrate the template; parameter values are placeholders pending calibration.

### R-LIQ-001 Allocatable money
- Inputs: `liquid_balance`, `operating_requirement`, `earmarked_total` (all minor units, same currency).
- Conditions: always evaluated first.
- Output: `allocatable = max(0, liquid_balance − operating_requirement − earmarked_total)`; if raw value < 0 → flag `SHORTFALL` with amount.
- Explanation: "Money available to assign after covering obligations until your next income and funds already set aside."
- Missing data: `operating_requirement` unknown → `allocatable = undetermined`, no discretionary allocations, reason `INSUFFICIENT_DATA_OPERATING`.
- Boundaries: exactly 0 → no allocation.
- Edge cases: multi-currency (compute per currency); negative balance (overdraft).
- Tests: invariant `sum(allocations) ≤ allocatable`; shortfall never yields positive discretionary allocation.

### R-RES-002 Starter buffer priority
- Inputs: `reserve_balance`, `starter_target`, `allocatable`, `critical_delinquency`, `structural_cf`.
- Conditions (ordered): if `critical_delinquency` → defer to survival rule. Else if `reserve_balance < starter_target` and `allocatable > 0` → allocate `min(allocatable, starter_target − reserve_balance)` to reserve.
- Output: priority `BUILD_STARTER_BUFFER`, allocation amount, remaining allocatable passed on.
- Explanation drivers: reserve balance, starter target, why target was chosen.
- Missing data: E unknown → starter target uses fixed floor parameter; flagged `ESTIMATED_TARGET`.
- Boundaries: `reserve_balance == starter_target` → rule inactive (hysteresis: reactivate only if balance falls below target − margin).
- Tests: P1, P2, P5 fixtures; boundary at target ± 1 minor unit.

### R-DEBT-003 Extra-payment ordering
- Inputs: debts with `effective_annual_cost`, `balance`, `criticality`, `days_past_due`, `promo_expiry`, `prepayment_penalty`; `extra_debt_budget`.
- Conditions: required payments already reserved. Strategy parameter ∈ {avalanche, snowball, cost_band_snowball, cash_flow_release}. Delinquent debts first (risk-first overlay). Debts with unknown cost excluded from cost ranking and placed after known high-cost debts, flagged.
- Output: ordered list; allocation to first target until paid, remainder to next; deterministic tie-breakers (cost desc, balance asc, debt_id asc).
- Explanation: strategy name, target debt, reason code (`HIGHEST_COST`, `SMALLEST_BALANCE`, `DELINQUENT_FIRST`, `PROMO_EXPIRING`), estimated interest saved (labeled estimate).
- Missing data: all rates missing → do not claim cost optimization; use snowball or user preference, reason `COST_UNKNOWN`.
- Edge cases: see `debt-framework.md` §17.
- Tests: tie cases, single-debt, penalty > savings, budget = 0, language switch.

### R-GOAL-004 Completed goal stop
- Inputs: goal `funded`, `target`, `status`.
- Conditions: `funded ≥ target` or `status ∈ {completed, cancelled}` → contribution = 0; overflow `funded − target` released as event `GOAL_OVERFLOW_RELEASED`.
- Tests: invariant "completed goals receive 0"; target lowered below funded.

## 5. Missing-data policy

Every input group resolves to one behavior:

| Behavior | When | Output |
|---|---|---|
| `PROCEED` | data known with adequate confidence | normal output |
| `PROCEED_WITH_CAVEAT` | minor gaps; conservative default applied | output + caveat + what data would refine it |
| `DEGRADE` | key input missing; a safer subset of logic can still run | reduced output (e.g., no cost ranking, no investable amount) |
| `ABSTAIN` | decision depends on unknown critical data | no recommendation; ask for the specific data |

Rules:
- Unknown ≠ zero. Unknown rate ≠ 0%. Unknown income ≠ last month's income. Unknown reserve ≠ none (but also ≠ adequate).
- Conservative defaults must be named parameters, versioned, and visible in explanations.
- Confidence propagates: any output depending on an estimate is marked estimated.
- Never let AI fill missing values for production decisions.

## 6. Thresholds, boundaries and hysteresis

- All thresholds are named parameters in a versioned configuration, not literals in code.
- Each threshold documents: value, unit, inclusive/exclusive side, rationale, source (reference concept or approved evidence), approval.
- Test each threshold at `value − ε`, `value`, `value + ε` with ε = 1 minor unit or the smallest meaningful unit.
- **Hysteresis:** entering and exiting a state use different thresholds or require persistence across N periods, preventing monthly flip-flopping.
- Ratios with a zero denominator (e.g., zero income) must have explicit behavior.

## 7. Invariants

Enforced as property-based tests on randomized and fixture inputs:

1. Allocations never exceed allocatable money: `Σ allocations ≤ allocatable`.
2. Negative available cash never produces positive discretionary allocation.
3. Required payments are reserved before any extra allocation.
4. Completed or cancelled goals receive no contributions unless explicitly reactivated.
5. Language/locale changes never alter amounts, orderings, priorities or reason codes.
6. Duplicate transactions (re-imported or re-parsed) do not change state or strategy.
7. Missing data never becomes fabricated certainty (no estimated value presented as known; no decision marked high-confidence when a required input is missing).
8. Determinism: identical inputs + rule version → identical outputs (no clocks, randomness or network in rule evaluation; "now" is an input).
9. Order independence: permuting transaction order within a period does not change results.
10. Internal transfers do not change income, expenses or net worth.
11. Currency integrity: no arithmetic across currencies without an explicit dated conversion.
12. Rounding conservation: allocated parts sum exactly to the allocated total.
13. Illiquid assets and credit limits never count as emergency reserve.
14. Unrealized/expected income (e.g., aguinaldo not yet received) is never allocatable.
15. Higher-level priorities never displace an active survival condition.
16. Monotonicity sanity: increasing liquid balance (all else equal) never reduces reserve allocation below what it was, and increasing debt cost never lowers that debt's position in avalanche ordering.

## 8. Explainability contract

Every strategy output must be able to answer, from stored data alone:

1. **Current priority:** priority code + hierarchy level.
2. **Why:** reason code(s) that fired, in evaluation order.
3. **What data drove it:** the normalized driver values and their confidence (e.g., "reserve covers 0.4 months of essentials; target 1 month starter").
4. **What could change it:** the nearest thresholds and what change would cross them (e.g., "once the reserve reaches ₡X, priority moves to paying the card at 48% annual cost").
5. **Uncertainty:** which inputs were estimated or missing.

Explanations are assembled from reason codes + parameters via localized templates, with no generative rewording. Output text should be validated so numbers in text match numbers in the decision record.

## 9. Profile-matrix testing

Every rule (and every rule-set change) must be run against a fixture matrix covering at least:

| # | Fixture | Key state | Expected emphasis |
|---|---|---|---|
| 1 | Low capital / no debt | coverage < starter, no debt, CF > 0 | starter buffer, sinking funds |
| 2 | Low capital / debt | coverage < starter, card debt, CF > 0 | buffer then debt split |
| 3 | Over-indebted | essentials + required payments ≥ income | criticality order, no extra plan, restructuring scenario |
| 4 | High capital / debt | reserve ≥ target + excess; high-cost debt | pay debt from excess; keep reserve |
| 5 | High capital / no debt | reserve ≥ target, no debt | no more reserve contributions; goals/long-term |
| 6 | High income / negative CF | top income, CF < 0 | stability, not investing |
| 7 | Variable income | high variance, some deficit months | baseline budgeting, larger reserve |
| 8 | No emergency reserve | reserve = 0 | starter buffer first |
| 9 | Strong emergency reserve | reserve ≥ target | stop contributions, redirect |
| 10 | Multiple competing goals | Σ required contributions > capacity | ordering, shortfall shown, completed goals 0 |

Recommended additions: strong assets / weak liquidity; mortgage-only low-cost debt with large reserve; USD debt with CRC income; first-month user (minimal history); critical delinquency while holding investments; windfall/aguinaldo month; all data missing.

For each fixture, tests assert: priority code, allocations, reason codes, invariants, explanation drivers, and behavior under the missing-data variant of the same fixture. Fixtures are **synthetic** — never derived from a real user's records.

A rule change must report a diff of outputs across the whole matrix; unexpected changes in unrelated fixtures block approval.

## 10. Test types

- **Unit:** each predicate and calculation.
- **Boundary:** each threshold at −ε / = / +ε.
- **Property-based:** invariants over generated states.
- **Metamorphic:** language switch, transaction reordering, duplicate injection, adding an internal transfer, scaling all amounts by a constant (ratios/priorities unchanged where expected).
- **Golden/snapshot:** full matrix outputs stored per rule-set version.
- **Regression:** past bugs as permanent fixtures.
- **Simulation:** multi-period runs (e.g., 24 months) to check transitions, hysteresis, payoff completion and rollover.

## 11. Rule lifecycle and versioning

```
proposed → specified (template complete) → implemented behind flag
 → tested (matrix + invariants + simulation) → human review → approved/rejected
 → released (versioned) → monitored (privacy-safe metrics) → revised or retired
```

- Rule sets are versioned; each decision records the version used.
- Old versions remain reproducible for audit.
- Parameter changes are rule changes (same approval path).
- Rollback path defined before release.

## 12. Financial learning loop (privacy-gated)

Permitted flow:

```
privacy-safe sanitized/aggregated evidence
 → offline analysis (an analyst or offline tooling, on sanitized aggregates only) identifies a pattern
 → hypothesis
 → proposed rule (template §3)
 → simulation across synthetic profiles (matrix §9 + generated)
 → automated tests (§10)
 → human review
 → approve / reject (recorded)
 → deterministic, versioned DINCR rule
 → observe privacy-safe outcomes → next iteration
```

Forbidden flow: `raw user financial history → automatic skill knowledge` (or → automatic rule change).

Evidence requirements:
- Aggregated with minimum group sizes (so no individual is inferable); no per-user rows leave the production boundary.
- Sanitized: no identifiers or free text (see list below); amounts bucketed or expressed as ratios.
- Documented: what was aggregated, how, and why it supports the hypothesis — in general terms.
- Observations are hypotheses until validated; correlation is not treated as a rule.

Never stored in this skill or in rule proposals: names, emails, phone numbers, account IDs, workspace IDs, raw transactions, transaction descriptions, salaries tied to people, bank statements, raw emails, PDFs, or identifiable financial profiles.

What may become durable skill knowledge: validated, generalized, privacy-safe financial principles, rule patterns, edge cases and thresholds with their rationale — phrased so no user could be identified from them.

## 13. Rule review checklist

- [ ] Template sections 1–8 complete.
- [ ] Financial rationale tied to a reference concept.
- [ ] No profile-name branching; logic uses state variables.
- [ ] All thresholds parameterized, versioned, boundary-tested, with hysteresis where relevant.
- [ ] Missing-data behavior defined per input.
- [ ] All invariants pass.
- [ ] Profile matrix run; diff reviewed.
- [ ] Multi-period simulation passes.
- [ ] Explanation answers priority / why / drivers / what-could-change / uncertainty.
- [ ] No AI dependency at decision time.
- [ ] Privacy review of any evidence used.
- [ ] Human approval recorded.
