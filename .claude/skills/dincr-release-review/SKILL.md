---
name: dincr-release-review
description: Final engineering and release review for DINCR, including the mandatory PR preflight (branch from current main, base=main, real diff and commits, merge=deploy gates). Use after implementing features, fixes or audits, before declaring work complete, before opening or updating a PR, and whenever someone claims a change is already in main.
---

# DINCR Release Review

A change is not complete because code was written or CI is green. Completion requires evidence appropriate to the risk. Validation levels, never overstated:

implemented → code-reviewed → automated-tested → integration-tested → physically validated → production-validated.

## 1. PR preflight (mandatory, before every PR and hand-off)

```
git fetch origin
git merge-base origin/main HEAD      # a commit of origin/main (not another branch's tip)
git log --oneline origin/main..HEAD  # exactly this task's commits
git diff --stat origin/main...HEAD   # exactly this task's files
gh pr view --json baseRefName,headRefName   # base must be main
```

Check that:
- the branch was created for this task from the current `origin/main`, and is not a reused or older branch;
- the PR base is `main`. A PR based on another branch is stacked: it needs explicit human authorization, and it lands in `main` only if that base branch is merged afterwards;
- `origin/main..HEAD` contains no commits of another open PR (hidden stacking) and nothing unrelated;
- after merge, the commits would really be in `main`.

**"Merged" claims.** When anyone (including you) says a change "was merged", verify the content, not the label: `git merge-base --is-ancestor <sha> origin/main`, or the file/diff on `origin/main`. A PR merged into an already-merged base branch never reaches `main`.

## 2. Merge = possible deploy

Merging to `main` can deploy the backend. List everything production must have **before** the new code runs:
- migrations;
- env vars and secrets;
- OAuth/console configuration;
- redirect URIs and scopes;
- incompatible changes.

Mark each as **PRE-MERGE GATE**. The PR is not merge-ready until a human confirms each gate. Never claim production state you haven't verified. A migration in the diff always produces a gate: either "must be applied before merge" or "safe to apply after, because …".

## 3. Scope

The change solves the requested problem and nothing else:
- no unrelated features, refactors or files;
- no debug leftovers;
- no new dependencies without need.

Out-of-scope findings are reported, not fixed.

## 4. Correctness and regression evidence

- **Root cause:** is it identified, or only the symptom?
- **Regression test:** is there a test that fails without the change? Show it: old code or a mutation.
- **Edge cases:** missing data, boundaries, running twice, failure halfway, stale state, two users, two workspaces, the Owner.
- **Neighbors:** nearby behavior that could regress, tested according to real dependencies.
- **Financial data:** apply `dincr-data-integrity` and `dincr-finance`:
  - reads don't write;
  - unknown ≠ zero;
  - declared vs imported precedence;
  - no double counting;
  - idempotency.

## 5. Security and privacy

Check:
- authentication, authorization and tenancy (`account_id` + `workspace_id`);
- the Owner↔Users boundary in both directions;
- OAuth binding, secrets and logs;
- analytics;
- no generative-AI path (`test_no_generative_ai.py`).

Use `dincr-mobile-security-qa` for depth.

## 6. Engineering guards

- File-size budgets: not raised, and not met by squeezing or joining lines.
- The CI guards (`PR guards` workflow, `test_engineering_guards.py`, `test_read_surfaces_are_read_only.py`) pass or have a justified, human-applied override label.
- `check_public_secrets.py` passes.

## 7. Mobile and i18n (Users-facing changes)

- Android and iOS: layout, safe areas, keyboard, sheets, lifecycle, deep links, cold start, offline/retry.
- Spanish and English: no Spanglish, no FINVA/JARVIS residue, language affects presentation only.

## 8. Tests

Run in risk order: focused, then subsystem, then the full suite at the final checkpoint. Record exactly what ran and its real result. For each failure, say whether it is:
- caused by the change;
- pre-existing;
- environment-specific;
- flaky;
- unknown.

Never invent results.

## 9. Final report

- **Result:** READY FOR HUMAN REVIEW, or NOT READY (with the reason).
- **Preflight:** base SHA of `origin/main`, branch, `base=main`, commits.
- **Changed:** what actually changed.
- **Validation:** tests and checks, with results.
- **Findings:** only meaningful ones, by severity.
- **PRE-MERGE GATES:** migrations, env, config, OAuth.
- **Remaining validation:** physical, manual, production.

Do not merge, deploy, migrate, change secrets, publish or delete production data.
