# DINCR — project instructions for Claude

Persistent operating manual for the main Claude session in this repository. Reusable knowledge and processes live in skills; this file holds the permanent repo rules. Do not duplicate skill content here.

## 1. Identity and source of truth

- The public product is **DINCR**. FINVA and JARVIS survive as historical/internal names in code, tables, routes and folders; do not rename them unless a task explicitly asks.
- DINCR is a mobile product (Android/iOS via Capacitor). `dincr.com` is landing, legal and support only, not a public web app.
- Plans: Free, Basic, VIP, and Owner. Owner is internal (DINCR Owner / JARVIS) and must never become a public plan.
- The repository and the current code are the technical source of truth. Inspect the existing implementation before assuming architecture or behavior.
- Layout: `jarvis-personal/backend` (FastAPI, Supabase/Postgres), `jarvis-personal/frontend` (React + Vite + Capacitor; public app in `src/users`, `src/products/finva`, `src/pages`; Owner in `src/personal`, `src/products/jarvis`), `jarvis-personal/frontend/landing` (dincr.com).

## 2. Skills

Load only the skills that are materially relevant to the task; never all of them by default.

| Skill | Slug | Use for |
|---|---|---|
| DINCR Core | `anthropic-skills:dincr-core` | any work on this repo or DINCR product decisions |
| Efficient Coding | `anthropic-skills:efficient-coding` | development, debugging, audits, long tasks |
| DINCR Finance | `anthropic-skills:dincr-finance` | financial logic, strategy, debts, goals, cash flow, recommendations |
| Mobile & Security QA | `anthropic-skills:mobile-security-qa` | auth, OAuth, RLS, sensitive data, mobile lifecycle, deep links |
| Release Review | `anthropic-skills:release-review` | final review before declaring work done or opening a PR |
| Autonomous Workflows | `anthropic-skills:autonomous-workflows` | several delegated tasks or unattended work |
| Skill Evolution | `anthropic-skills:skill-evolution` | turning durable lessons into skill improvements |

Skills = reusable knowledge and process. CLAUDE.md = permanent repo rules.

## 3. Agents

Project agents in `.claude/agents/`. Delegate only when it adds value; never launch all of them mechanically. For trivial changes, work directly when delegating would cost more context or time than the change itself.

- **explorer** (read-only): investigate a flow, locate an implementation or find a root cause before editing.
- **implementer**: concrete, bounded changes once the problem is understood.
- **reviewer** (read-only): after significant changes, or before treating a task as ready for PR/human review.
- **security-reviewer** (read-only): only when a change touches or may affect authentication, authorization, OAuth, sessions, roles, Owner/User isolation, Supabase/RLS, secrets, financial data, account/data deletion, analytics/privacy, deep links, bank email parsers or other sensitive operations.

explorer, reviewer and security-reviewer have no shell and cannot run `git diff`. Give them what they need: changed files, relevant paths, or a patch saved to a readable file.

## 4. Normal development flow

Understand → inspect the existing implementation → investigate if needed → implement the smallest correct change → focused tests → independent review when warranted → security review when warranted → fix findings → final relevant validation → commit → push → PR → checkpoint.

A task is not done because it compiles. Always report separately what was:
- validated automatically,
- requires physical/manual validation,
- not validated.

Never claim a physical test happened if it did not.

Validation commands (from `jarvis-personal`): `python -m pytest backend -q`. From `jarvis-personal/frontend`: `npm run build`, `npx eslint .`, the relevant `npm run test:*` scripts (CI runs them all), and `npm run build:landing` before `npm run test:landing`. Report pre-existing failures separately from regressions.

## 5. Autonomous work / overnight queue

When the user delegates several tasks or authorizes unattended work, use Autonomous Workflows:
- order tasks by dependency first, then continue from one task to the next without asking "should I continue?" between routine tasks;
- if a task is blocked, record the blocker and continue with independent tasks;
- keep every task auditable.

Prefer separate branches/PRs for independent tasks when that reduces conflicts and allows independent review. For dependent tasks use an explicit, documented strategy (e.g. stacked branches/PRs). Never mix unrelated changes to reduce the number of PRs.

## 6. Worktrees

Do not use a worktree for every change. Use isolation/worktrees when there are parallel tasks, a significant change, a risk of contaminating another branch, implementer agents working in parallel, or a task that depends on keeping another branch intact. For small sequential changes, avoid the extra complexity.

## 7. Context and compaction

Durable state lives in Git, PRs, tests and checkpoints, not only in the conversation. Before a major compaction and after each autonomous task, keep a compact checkpoint: task, branch, status, relevant files/changes, commit (if any), tests and results, pending findings, pending physical validation, next action.

After a compaction, rebuild state from the checkpoint plus Git before continuing. Do not rescan the whole repository without need.

## 8. Efficiency

Apply Efficient Coding: targeted search before broad reading, progressive disclosure, no full-tree reads without need, focused tests instead of repeated full suites (run broad validation when risk or release stage justifies it), no agents when they add nothing, little narration during autonomous work, evidence over speculation, reuse existing implementation and tests.

Never trade correctness, security or privacy for saved tokens.

## 9. Security and privacy

Never:
- commit secrets, or show full secrets in reports;
- weaken auth, RLS or Owner isolation to make a test pass;
- send sensitive financial data to logs or analytics;
- turn raw user financial data into reusable knowledge automatically.

Financial learning path: sanitized/aggregated data → general hypothesis → synthetic tests → deterministic proposal → human review → approved, versioned rule.

## 10. Human gates

Autonomous work may inspect, create branches, edit, run local tests, use agents, commit, push, and create/update PRs.

Without explicit human approval, never:
- merge into `main`;
- deploy to production;
- run production migrations;
- change production secrets or configuration;
- delete production data;
- publish to Google Play or the App Store;
- take destructive or irreversible external actions.

When a task reaches one of these gates, prepare it up to the gate, document it, and move on to another independent task if there is one.

## 11. Git / PR discipline

Before editing: check the branch and working tree, understand the base and dependencies, and do not contaminate an existing branch. Do not commit the user's unrelated local changes.

Every PR: clear scope, only related changes, relevant tests, stated risks and pending validation, and no claims beyond what was actually tested.

Never force-push or rewrite shared history without explicit human authorization.

## 12. DINCR engineering principles

- Deterministic, auditable behavior first. AI proposes; deterministic DINCR executes; humans approve high-impact rule changes.
- No feature creep during fixes or audits.
- Mobile lifecycle matters: cold/warm start, background/foreground, offline/retry, keyboard, safe areas, deep links.
- Keep Users and Owner strictly separated.
- i18n changes presentation, never financial meaning.
- Analytics stays free of identifiable financial or sensitive information.
- For financial rules use DINCR Finance and require human review for high-impact changes.

## 13. Skill Evolution

After substantial work, briefly check whether a durable lesson appeared. If not, do nothing. If so, low-risk operational/efficiency improvements may be proposed or applied per Skill Evolution; financial, security, privacy, product, legal/regulatory or other high-impact changes require human approval. Prefer improving existing skills over creating a new one per problem.

## 14. Handoff

At the end of an autonomous session, report compactly:

- **Completed:** task → branch/PR → result
- **Blocked:** task → reason
- **Validation required:** pending physical/manual tests
- **Important findings:** only those that change a decision or need attention
- **Next human action:** the concrete action needed from the user

No long logs of everything that was done.
