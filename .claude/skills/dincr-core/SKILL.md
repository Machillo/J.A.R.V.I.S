---
name: dincr-core
description: Core product, architecture, tenancy, Owner-boundary, determinism and privacy rules for DINCR. Use whenever working on the DINCR / J.A.R.V.I.S repository or making technical or product decisions about DINCR.
---

# DINCR Core

DINCR is a Costa Rica-first personal-finance **mobile** product (Android/iOS via Capacitor). This Skill holds the product and architecture invariants behind `CLAUDE.md` §4. Where they overlap, `CLAUDE.md` wins.

## Product identity

- **One public product: DINCR.** There is no public DINCR web application. dincr.com is marketing, legal and support only. Do not ship financial features to the web by accident.
- **Legacy names:** JARVIS and FINVA are internal names. Never expose them publicly, and never mass-rename historical routes, folders, tables, env vars or infrastructure only because they contain those words.
- **Public UI:** uses DINCR branding. No Owner/internal terminology and no legacy assistant personality.

## Plans and the Owner boundary

- **Plans:** Free, Basic, VIP and Owner. Owner is private and internal: it is never a purchasable plan and its features are never exposed to users.
- **Owner-only behavior** lives behind an explicit server-side boundary: a role check, an internal router, or a module used only by Owner routes. Hidden UI is not a boundary.
- **The boundary runs both ways.** Users must not reach Owner features, and **nothing private to the Owner may influence a User**: identity, names, contacts, aliases, accounts, IBANs, cards, heuristics, configuration or data. Owner-specific heuristics must never be the default behavior of code that Users run.
- **The Owner as a user:** when the Owner uses a normal DINCR feature (e.g., connecting a mailbox), it goes through the same flow and isolation as any account. There is no role bypass.

## Shared code is neutral

Code that Users and the Owner share — parsers, ingestion, finance and strategy engines, notifications — must:

1. receive the account/workspace context (and the holder's identity, if needed) **explicitly** from the caller;
2. be **neutral by default** when that context is absent: no personal names, accounts or contacts;
3. fail safe when a required context is missing, never falling back to "the Owner" or "the first user";
4. keep private configuration (Owner env settings) reachable only from Owner-only code.

When a shared engine was historically built for the Owner, reusing it for Users requires checking every input it reads. Payroll models, cash balances, automations and personal accounts assumed for the Owner must not silently apply to Users.

## Tenancy

- **Scope:** every read and write of user data is scoped by `account_id` + `workspace_id` wherever the model has them.
- **IDs:** a client-supplied ID never grants access outside the caller's workspace.
- **Non-interactive paths:** crons, webhooks, OAuth callbacks, Pub/Sub, background jobs and parsers need the same isolation as interactive requests. When there is no session, they carry the account/workspace explicitly from a trusted source (the connection row, the signed/stored flow).

## Determinism and AI

- **No generative-AI runtime** for user data or financial decisions. Mail (Gmail/Outlook), bank documents and anything derived from them (transactions, aggregates, detected accounts) never reach OpenAI, Gemini or any generative provider.
- **Guard:** `backend/test_no_generative_ai.py` walks the application import graph and fails if any reachable module can talk to such a provider.
- **Parser Discovery:** offline developer tooling on sanitized samples, outside the application. Humans turn its proposals into deterministic parsers with synthetic tests.
- **Calculations:** financial calculations are deterministic and reproducible, and never depend on language, UI or generated text.
- **History:** old documentation describing AI behavior is history, not current behavior. Don't reintroduce AI because a historical module had it.

## Product philosophy

Reduce manual financial work: if a value can be safely discovered, calculated or updated automatically, don't make the user type it. But discovered data must never silently overwrite what the user declared: see `dincr-finance` → `references/data-precedence.md`. The differentiator is trustworthy automation, not an AI chat.

## Privacy

Minimize collection. PostHog and logs never receive:
- names, emails, phone numbers;
- real user/account/workspace IDs;
- amounts, salaries, balances, debts, transaction descriptions;
- mail/PDF content or free-form financial text;
- OAuth tokens/codes or secrets.

No autocapture or session recording without explicit approval. Fixtures are synthetic: never real people, accounts or messages.

## Mobile and i18n

- **Mobile-first:** narrow screens, safe areas, keyboard, sheets, scrolling, Android/iOS lifecycle, deep links and cold starts. Don't optimize for desktop web.
- **Language:** changes presentation, never financial meaning. User data is not translated; canonical persisted values are language-independent. Legal documents are not translated without approval.

## Release discipline

Priorities, in order:
1. security, privacy and data integrity;
2. launch blockers;
3. regressions;
4. reliability;
5. mobile UX consistency;
6. tests.

No feature creep during stabilization: document unrelated findings instead of fixing them. Production actions (merge, deploy, migrations, secrets, data deletion, store publishing) are human-gated (`CLAUDE.md` §3, §6).

## Source of truth

The current repository beats stale documentation. If instructions conflict with the code or with an explicit task instruction, surface the conflict; don't guess.
