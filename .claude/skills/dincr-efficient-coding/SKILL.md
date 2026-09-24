---
name: dincr-efficient-coding
description: Work efficiently on the DINCR repository — targeted investigation, small auditable reversible changes, risk-based testing, no budget gaming, no incidental refactors — without sacrificing correctness. Use for development, debugging, audits and long-running tasks.
---

# DINCR Efficient Coding

Spend computation where uncertainty and risk are high, not on rediscovering what can be read directly. Priority order: correctness, then efficiency, then brevity.

## Investigate progressively

1. **Setup:** read the task. Run `git status` and check the current branch; for a new task, run the `CLAUDE.md` §2 preflight first.
2. **Search:** look for exact symbols, routes, errors or strings (grep/rg, `git log -S`, `git diff`).
3. **Read:** open only what the execution path needs: lines → function → file → neighbors → architecture.
4. **Re-reads:** don't reread unchanged files, and don't scan the whole repository unless the task is repository-wide.

## Change small, auditable and reversible

- The smallest correct change that fits existing patterns.
- **No incidental refactors,** renames, formatting churn or one-off abstractions. No new dependencies when existing tools suffice.
- **One problem per change.** Don't fix twenty things because you noticed them while fixing one. Report the others as findings: path, why it matters, severity and a suggested separate PR.
- **No budget gaming.** Never meet a file-size budget by squeezing lines, joining statements, JSX or HTML onto one line, moving code into long comments, or reducing readability. Never raise the limit to pass CI. If a file outgrows its responsibility, extract a coherent module, and say so.
- Keep changes reversible. No destructive data operations as part of a fix.

## Test by risk

1. Syntax, static and focused tests for the changed code.
2. Related subsystem tests.
3. The full suite at the final checkpoint (always for financial, security or CI changes).

For bugs, a regression test that fails without the fix, shown failing. Never skip required security or financial tests to save time.

## Debug with evidence

Reproduce → locate the failing path → gather evidence → form the smallest hypothesis → test it → change the code. Don't try several speculative fixes at once.

## Subagents

Use them only for independent, parallel or isolated work, or for specialized review. Not for a single search, a one-file read or a small edit. If a project role can't be loaded by the host, don't pretend it ran.

## Long work and communication

- **Checkpoint:** keep a compact one (objective, branch, done, state, findings, tests, remaining, blockers). Git is the durable memory.
- **Updates:** report discoveries, decisions, blockers and results, not routine tool calls.
- **Final reports:** what changed, why, tests, risks, gates and remaining manual validation.

## Stop and ask for

Destructive operations, production deploys, database changes, secrets, irreversible actions, high-impact product decisions and human-reserved actions. Routine implementation choices don't need confirmation.
