---
name: dincr-finance
description: Deep personal-finance reasoning framework for DINCR across financial profiles, from over-indebted and low-liquidity users to debt-free high-capital users. Use when designing, reviewing, testing or improving DINCR financial logic, strategy, debts, savings, goals, income, cash flow, emergency funds, capital allocation, reconciliation of declared versus imported data or financial recommendations — including deterministic strategy rules, profile-matrix tests, invariants, windfalls/aguinaldo handling and privacy-safe rule improvement, even if the request only mentions one of these.
---

# DINCR Finance

DINCR serves users across the full spectrum of personal financial situations. Never assume one strategy fits everyone, and never reduce reasoning to one universal formula.

## Non-negotiables

1. **Unknown ≠ zero.** Missing data is missing: it is not a zero balance, zero income or zero debt. Communicate uncertainty rather than fabricate precision.
2. **Declared vs observed.** Partial or imported evidence must not silently destroy a valid value the user declared. Reconciliation follows an explicit, deterministic, tested policy: `references/data-precedence.md`.
3. **Reads don't change financial truth.** Computing a dashboard, strategy, report or projection never records payments, reduces debts, moves balances or advances goals. See `dincr-data-integrity`.
4. **Determinism.** Identical inputs plus rule version give identical outputs. No generative AI at decision, parse or presentation time.
5. **Idempotency and dedupe.** Re-importing, re-parsing, retrying or reconnecting a mailbox never changes state or strategy. Internal transfers are never income, expense or net-worth change.
6. **Isolation.** Every figure comes from the caller's own account/workspace. Owner-specific engines, payroll models or balances never become a User's defaults.

## Core principle: strategy is state-dependent

Before evaluating a recommendation, understand the user's state:
- cash flow and liquidity;
- debt burden, cost and urgency;
- income stability and essential obligations;
- emergency resilience;
- goals and horizons;
- available capital, risk capacity and life constraints.

Don't infer health from income or balance alone. Separate temporary problems from structural ones.

## Financial hierarchy

SURVIVAL → STABILITY → RESILIENCE → DEBT OPTIMIZATION → GOALS → WEALTH BUILDING → WEALTH OPTIMIZATION

- Lower-level risks constrain higher-level optimization.
- Users move down as well as up, so re-evaluate every period.
- Never recommend aggressive optimization while survival is unresolved.

Details: `references/financial-framework.md`.

## Decision philosophy

- **Tradeoffs.** Separate mathematical optimization, liquidity protection, risk reduction, behavioral practicality and long-term wealth. The highest-return action is not automatically the safest.
- **Debt and reserves.** Debt is a tool with costs and risks, never "all debt is bad". Reserve size is contextual.
- **Explanations** reveal which consideration dominated.

## Designing a production rule

State:
1. the rationale;
2. the normalized inputs;
3. the deterministic conditions;
4. the output;
5. the explanation and the missing-data behavior;
6. the thresholds and their boundaries;
7. the edge cases;
8. the tests across contrasting profiles and boundary values;
9. that language does not affect it;
10. human approval before production.

Production logic branches on normalized state, never on a profile name or a person. Thresholds are named, versioned parameters. Implementation-specific formulas (e.g., a specific income-policy version) live in code and its tests, not as universal rules here.

Template, invariants, profile matrix and test types: `references/dincr-strategy-rules.md`.

## Safety

- **No guarantees.** Never guarantee outcomes or returns.
- **Education vs advice.** General education is not individualized regulated advice.
- **Jurisdiction.** Verify current rules (aguinaldo, usury caps, securities) before implementing jurisdiction-specific behavior.

## Privacy and the learning loop

- **Allowed path:** sanitized, aggregated evidence → hypothesis → rule proposal → synthetic simulation → tests → human review → versioned deterministic rule.
- **Never allowed:** raw user financial history → skill knowledge or automatic rule change.
- **Never stored** here, in references, fixtures or proposals: names, emails, phones, account/workspace IDs, raw transactions or descriptions, salaries tied to people, statements, emails, PDFs.

## References — load only what the task needs

| If the task involves… | Load |
|---|---|
| Declared vs imported/discovered values, partial evidence, reconciliation, precedence, unknown values | `references/data-precedence.md` |
| Financial state, hierarchy level, prioritization, transitions, health scoring | `references/financial-framework.md` |
| Test personas, contrasting situations, state changes | `references/financial-profiles.md` |
| Debts: cost, minimums, delinquency, avalanche/snowball, prepayment, refinancing | `references/debt-framework.md` |
| Cash buckets, reserves, sinking funds, variable income, goals, windfalls, aguinaldo | `references/savings-liquidity.md` |
| Investable capital, risk, allocation, regulated-advice boundaries | `references/wealth-investing.md` |
| Writing or reviewing a production rule, invariants, thresholds, tests, versioning | `references/dincr-strategy-rules.md` |
