# Data precedence and reconciliation

DINCR combines what the user **declares** (profile: income, savings, expenses, debts, goals) with what it **observes** (manually recorded movements, bank emails, statements, detected accounts). Observation is usually partial. This reference defines how the two meet without silently destroying correct data.

## Source classes

| Class | Examples | Typical completeness |
|---|---|---|
| Declared | Profile income, declared savings, declared expenses, debts entered by the user | Intentional, possibly stale |
| Recorded | Movements the user types in | Intentional, possibly incomplete |
| Imported | Accepted bank-email or statement movements | Incomplete by nature: partial scan window, unsupported senders, banks that don't notify every movement, pagination |
| Discovered | Accounts detected from mail, balance often unknown | Existence known, value frequently unknown |
| Derived | Averages, projections, baselines | Only as good as their inputs |

## Principles

1. **Unknown ≠ zero.** An unknown balance, an income not yet observed or a month not fully scanned is missing, not zero. Store unknown as null or unknown, exclude it from sums and state it in explanations.
2. **Absence of evidence is not evidence of absence.** No imported income this month does not mean no income. A few imported expenses do not mean the month's spending is known.
3. **Partial observation never silently replaces a declaration.** Import or discovery may *complement*, *confirm* or *flag* a declared value. It may replace it only through an explicit rule that says when the observation is complete enough, and that rule is tested.
4. **Direction matters.** Conservative corrections (e.g., capping a declared income by consistent, user-entered evidence of a lower income) may be allowed by an explicit policy. Imported partial data must never both lower and raise a declared value by accident.
5. **No double counting.** Declared and observed values of the same thing are never added together. Recurring items are added only if they are not already part of the declared figure.
6. **Internal transfers are neutral.** Moving money between the user's own accounts never counts as income, expense or net-worth change. Ownership of both endpoints comes from the user's own confirmed accounts (their workspace), never from anyone else's configuration.
7. **Dedupe is semantic and per workspace.** The same movement seen by two mailboxes, a notification and a statement, or a reconnect/re-import, is one movement. Ambiguous matches stay for user review rather than being discarded.
8. **The same policy everywhere.** Screens and engines that show the same quantity (e.g., monthly income on Home and in Strategy) must use one shared, versioned policy, not independent interpretations.
9. **Explain the source.** Outputs should be able to say whether a value is declared, recorded, imported, estimated or missing.

## Designing a reconciliation policy

- **Scope:** what quantity, for which account/workspace, over which period.
- **Precedence:** which source wins, and under which completeness condition an observation may override.
- **Conservative caps:** which evidence may lower a value, and which evidence is excluded (typically imports).
- **Missing data:** what happens when each input is missing.
- **Double counting and internal transfers:** how both are excluded.
- **Versioning:** a policy version string surfaced for audit.
- **Tests:**
  - partial import;
  - import above the declared value;
  - no declared value;
  - only manual data;
  - variable income;
  - internal transfers;
  - another workspace present (isolation);
  - repeated import (idempotency);
  - the real regression that motivated the policy.
- **Approval:** changing precedence is a financial-rule change and requires human approval.

## Anti-patterns (each caused a real incident class)

- Treating a partial month of imported deposits as the monthly income.
- Replacing declared savings with detected accounts whose balance is unknown (stored as 0).
- Subtracting "income already received" when that money isn't counted anywhere else for this user.
- Letting an engine built for one person's payroll become the default for every user.
- Mutating debts or balances while *reading* a screen.
