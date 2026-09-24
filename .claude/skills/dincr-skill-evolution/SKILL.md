---
name: dincr-skill-evolution
description: Turn a real DINCR incident or repeated pattern into a durable, reviewed improvement of CLAUDE.md, a project Skill, a reviewer role or an automatic guard — through a PR, never by silent self-modification. Use after substantial work reveals a reusable lesson, or when a mistake shows an instruction was missing, ambiguous or contradictory.
---

# DINCR Skill Evolution

Instructions improve from evidence, conservatively, and only through reviewable changes.

## Rules

1. **No silent self-modification.** `CLAUDE.md`, `.claude/skills/**` and `.claude/agents/**` change only through a PR that a human reviews. Local plugin or auto-memory copies are not the source of truth. A lesson kept only in memory is not learned.
2. **Evidence first.** A change must come from a real incident or a repeated pattern, with a concrete example. Wording preferences don't qualify.
3. **Capture the class, not the incident.** Write the general rule ("a PR merged into an already-merged base never reaches main") without PR numbers, SHAs, people's names, amounts, prices, env-var names or one-off formulas.
4. **Prefer a guard over prose.** If a test or CI check can reliably detect the error class, add it. Keep it narrow and maintainable (behavioral tests or small allowlists, not sprawling regexes). Document what it doesn't cover instead of implying full protection.
5. **Put it in the right place:**
   - an invariant that must always apply → `CLAUDE.md`;
   - task-specific depth → the relevant Skill or its `references/`;
   - review checklists → the reviewer roles;
   - enforceable facts → tests and CI.
   Don't duplicate across layers; link instead.
6. **High-impact rules need explicit approval.** This covers financial rules and thresholds, security and authorization, privacy, Owner isolation, production safety, and product, legal or regulatory policy. Propose them with evidence, tests or simulation, and wait for approval.
7. **Privacy.** Never put real user data, identifiable financial information, secrets or personal names into instructions, references or fixtures. Generalize to synthetic examples first.

## Process

incident or pattern → root cause → is it reusable? → does an existing rule already cover it (and why did it fail)? → the smallest improvement (a rule, a guard or both) → a contradiction check across `CLAUDE.md`, the Skills and the roles → validation (the guard tests pass; a simulated task shows the rule would have prevented the error) → PR with a short rationale (problem, evidence, change, expected effect).

## Anti-bloat

- Improve existing Skills rather than adding new ones.
- Keep each `SKILL.md` concise and move depth into `references/`.
- Remove obsolete and contradictory instructions: they are as dangerous as missing ones. An old rule that allowed stacked PRs caused real losses.

If there is no durable lesson, change nothing.
