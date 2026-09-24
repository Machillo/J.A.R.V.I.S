# DINCR — project instructions for Claude

Always-loaded operating rules for this repository. The invariants in §2–§5 apply to every task and must never depend on a Skill being invoked. Deeper, task-specific guidance lives in the project Skills (`.claude/skills/`, §7); reviewer roles live in `.claude/agents/` (§8); what CI enforces is in §9.

## 1. Product and repository

- The public product is **DINCR**, a mobile product (Android/iOS via Capacitor). `dincr.com` is marketing, legal and support only: never build a second, web-based financial app there.
- Plans: Free, Basic, VIP and Owner. Owner is internal (DINCR Owner / JARVIS) and never purchasable.
- FINVA/JARVIS are historical internal names in code, tables, routes, folders and env vars. Do not rename them unless the task asks.
- The current code is the source of truth. Inspect it before assuming architecture or behavior.
- Layout:
  - `jarvis-personal/backend`: FastAPI, Supabase/Postgres.
  - `jarvis-personal/frontend`: React + Vite + Capacitor. Public app in `src/users`, `src/products/finva`, `src/pages`; Owner in `src/personal`, `src/products/jarvis`.
  - `jarvis-personal/frontend/landing`: dincr.com.
  - `jarvis-personal/database/migrations`: schema.

## 2. Git, branches and PRs (absolute defaults)

1. `git fetch origin` before starting any task.
2. Every new task starts from the **current** `origin/main`: `git checkout -b <new-branch> origin/main`.
3. One **new** branch per task. Never reuse a previous task's or PR's branch, even if it looks related.
4. Every PR has `base=main`.
5. **No stacking.** Never base a branch or PR on another unmerged branch or PR unless Kenneth explicitly authorizes that specific case. If the work depends on an unmerged PR, stop and report the dependency.
6. **`MERGED` is not proof.** A PR can be merged into a branch that was itself already merged, and its commits then never reach `main`. Whenever it matters whether a change is in `main`, check the content: `git merge-base --is-ancestor <sha> origin/main`, or the file or diff on `origin/main`.
7. Before delivering, run and check:
   ```
   git fetch origin
   git merge-base origin/main HEAD      # must be a commit of origin/main
   git log --oneline origin/main..HEAD  # only this task's commits
   git diff origin/main...HEAD          # only this task's changes
   gh pr view --json baseRefName        # must be main
   ```
8. Never force-push or rewrite shared history without explicit authorization.
9. Never commit unrelated local changes, secrets, `google-services.json` or the stray top-level `J.A.R.V.I.S/` folder. Stage files by name; never `git add -A`.

## 3. Merge = possible deploy

A merge to `main` can deploy the backend automatically. Before calling a PR merge-ready, identify everything production must already have when the new code starts:
- migrations;
- environment variables and secrets;
- external or OAuth configuration (consoles, redirect URIs, scopes);
- incompatible API or data changes.

If any of it must exist first, write **PRE-MERGE GATE** in the PR and in the report. The PR is not merge-ready while a gate is open.

Never run production migrations or destructive operations yourself, and never declare that production "has" something you have not verified.

## 4. Product invariants

**A. Users ≠ Owner, in both directions.**
- Users must not reach Owner features.
- Nothing private to the Owner may shape a User's data or behavior: identity, names, accounts, contacts, aliases, IBANs, cards, heuristics, configuration or data.
- Shared code (parsers, ingestion, finance engines, strategy) must:
  - be **neutral by default**;
  - receive the account/workspace context explicitly;
  - fail safe when context is missing;
  - never fall back to the Owner.
- Owner-only behavior sits behind an explicit Owner-only boundary: role check, internal router or Owner-only module.
- Never hardcode a person's name, account or contact in runtime code.

**B. Tenancy.**
- Every read or write of user data is scoped by `account_id` + `workspace_id` when the model has them.
- A direct ID must never let a caller escape its workspace.
- Background jobs, OAuth callbacks, parsers, webhooks and crons need the same isolation as interactive requests.
- OAuth started by one account/workspace can only be completed by that same session.

**C. Reads do not mutate financial truth.**
- GET, read, dashboard, report, strategy and preview paths are read-only by default.
- They must not:
  - reduce or change debts;
  - create payments or transactions;
  - change balances;
  - advance goals;
  - alter any other user financial data.
  The only exception is an explicitly documented and authorized command or automation.
- Do not hide financial writes inside helpers called from reads.
- Schema DDL (`ensure_*`, `CREATE TABLE IF NOT EXISTS`) during reads is legacy: do not add more. Schema belongs in migrations.

**D. Declared vs discovered data.**
- **Unknown ≠ zero.**
- Partial or imported evidence must not silently replace a valid declared value. Examples:
  - a partial month of imported deposits is not the monthly income;
  - a detected account with an unknown balance does not zero declared savings;
  - missing movements do not prove there was no income or expense.
- Reconciliation needs an explicit, deterministic, tested policy (DINCR Finance → `references/data-precedence.md`).

**E. Determinism, no generative AI at runtime.**
- DINCR has no generative-AI runtime for user data. Gmail/Outlook content, bank documents and any data derived from them are never sent to OpenAI, Gemini or any other generative provider.
- No plan may acquire an AI path by reusing historical code.
- Parser Discovery is offline developer tooling, kept outside the application.
- Do not reintroduce AI because a historical architecture had it. Comments and docs describing old AI behavior are history, not current behavior.

**F. Privacy.**
- No names, emails, IDs, amounts, descriptions, email/PDF content, tokens or secrets in logs, analytics or fixtures.
- Test data is synthetic. Real people's data never becomes a fixture, and raw user data never becomes reusable knowledge.

## 5. How to work

- **Root cause before patch.**
  - Reproduce the bug.
  - Separate the symptom from the cause.
  - Check whether other plans, workspaces, providers or the Owner are affected.
  - Add a regression test that **fails without the fix**; show it failing (old code or a mutation), then passing.
- **CI green is not proof of correctness.**
- **Small and auditable.** Stay in scope, make no incidental refactors, and report out-of-scope findings instead of fixing them. Separate blockers from cleanup.
- **File-size budgets are architecture, not a game.**
  - Never meet one by squeezing lines, joining JSX/HTML, or hurting readability.
  - Never raise one to get CI to pass.
  - Extract a coherent module instead.
  - A budget increase needs explicit human approval.
- **Validation commands.**
  - From `jarvis-personal`: `python -m pytest backend -q`, `python backend/scripts/check_file_size_budget.py`.
  - From `jarvis-personal/frontend`: `npm run build`, `npx eslint .`, the `npm run test:*` scripts (CI runs them all), and `npm run build:landing` before `npm run test:landing`.
  - Report pre-existing failures separately from regressions.
- **Report three categories separately:** validated automatically, needs physical/manual validation, not validated. Never claim a device test that did not happen.

## 6. Human gates

Autonomous work may inspect, branch, edit, run local tests, commit, push and open or update PRs.

Never do the following without explicit human approval:
- merge into `main`;
- deploy;
- run production migrations;
- change production secrets or configuration;
- delete production data;
- publish to the stores;
- take other destructive or irreversible external actions.

Prepare the work up to the gate, document it, and continue with independent work.

## 7. Project Skills (`.claude/skills/`)

Load only the Skills relevant to the task:

| Skill | Use for |
|---|---|
| `dincr-core` | Any DINCR work: product, architecture, plans, Owner boundary, privacy |
| `dincr-finance` | Financial logic, strategy, debts, goals, income, cash flow, data precedence |
| `dincr-data-integrity` | **Any change that reads or writes financial data**: read/command, tenancy, idempotency, imports, dedupe |
| `dincr-mobile-security-qa` | Auth, OAuth, mail providers, RLS, secrets, deep links, mobile lifecycle |
| `dincr-release-review` | Before declaring work done or opening a PR, including the PR preflight |
| `dincr-autonomous-workflows` | Several delegated tasks or unattended work |
| `dincr-efficient-coding` | Long tasks, audits, debugging |
| `dincr-skill-evolution` | Turning a real incident into a reviewed instruction or guard |

Skills and agents change only through a reviewed PR, never silently.

## 8. Agents (`.claude/agents/`)

- **The roles:**
  - `explorer`: read-only investigation;
  - `reviewer`: independent change review, including the PR preflight and data integrity;
  - `security-reviewer`: adversarial review of security, privacy, tenancy, Owner↔Users and AI boundaries.
- **The format** follows Claude Code's documented subagent format.
- **Loading:** some hosts, such as the desktop app, do not expose project agents as subagent types. If a role does not appear, run a `general-purpose` agent with that file's instructions, or do the review in the main session using the same checklist. Never claim an independent review happened when it did not.
- The roles have no shell. Give them the diff, for example a patch saved to a file.

## 9. Automatic guards (CI)

- **`PR guards` workflow** (`.github/workflows/pr-guards.yml` + `.github/scripts/pr_guards.py`):
  - the PR base must be `main`;
  - the PR must not contain another open PR's head (stacking);
  - a merge into a non-`main` branch is flagged;
  - a file-size budget may not be raised;
  - a new migration requires the `migration-gate-acknowledged` label.
  - Overrides are explicit labels, set by a human.
- **Engineering tests** (`jarvis-personal/backend/tests/test_engineering_guards.py`, `test_read_surfaces_are_read_only.py`): Owner configuration stays out of shared Users code; Users read surfaces cannot write financial tables; agent and Skill files are valid and portable.
- **Existing tests:**
  - `test_no_generative_ai.py`: no AI provider reachable from the app;
  - `check_file_size_budget.py`;
  - `check_public_secrets.py`;
  - the OAuth, tenancy and isolation tests.

Guards catch the known classes of error. They do not replace §2–§5.

## 10. Context, compaction and handoff

- Durable state lives in Git, PRs and tests, not in the conversation or auto-memory. Auto-memory may hold checkpoints; any rule that must survive belongs in this file, a Skill or a guard.
- **Checkpoint** (before compaction and after each autonomous task): task, branch, status, files, commits, tests, pending findings, pending physical validation, next action.
- **Handoff:**
  - **Completed:** task → branch/PR → result.
  - **Blocked:** task → reason.
  - **Validation required.**
  - **Important findings.**
  - **Next human action.**

## 11. What does not belong here

No PR numbers, SHAs, people's names, balances, prices, one-off formulas, operational env-var names, exact budget numbers (CI owns them) or single-migration details. Rules capture the class of error, not the incident.
