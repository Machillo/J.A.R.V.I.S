## What and why


## Preflight (CLAUDE.md §2)
- [ ] Branch created for this task from the current `origin/main`, not reused and not stacked.
- [ ] Base is `main`. `git log origin/main..HEAD` contains only this task's commits.
- [ ] `git diff origin/main...HEAD` contains only this task's changes.

## PRE-MERGE GATES (merge = possible deploy)
- [ ] None, or listed here: migrations, env vars and secrets, OAuth/console config, incompatible changes.

## Evidence
- [ ] Root cause identified. A regression test fails without the change (shown) and passes with it.
- [ ] Tests run, with real results. Pre-existing failures listed separately.
- [ ] Data integrity (reads don't write, tenancy, unknown ≠ zero, declared vs imported) where financial data is touched.
- [ ] Security and privacy (Owner↔Users both ways, OAuth, secrets, no generative AI) where relevant.

## Not validated / needs a device or production check

