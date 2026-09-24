---
name: dincr-mobile-security-qa
description: Security, privacy and mobile QA framework for DINCR. Use when implementing or reviewing authentication, authorization, tenant isolation, the Owner/Users boundary, OAuth, Gmail/Outlook mail connections, Supabase/RLS, secrets, sensitive financial data, account deletion/export, analytics, React/Capacitor mobile behavior, Android/iOS lifecycle, deep links, offline behavior or release-critical changes.
---

# DINCR Mobile & Security QA

Don't only ask whether the legitimate user can do something. Ask what happens when the environment, network, session, another account or an attacker behaves differently. Correctness, privacy and data integrity beat convenience.

## Adversarial questions

For every change ask:
- Can a different user or workspace do this?
- Can a stale session do it?
- Can the request be replayed?
- Can an identifier be substituted?
- Can a client bypass the UI and call the endpoint directly?
- Can state from one account affect another?
- Can sensitive data escape through a response, log, error or analytics?

Frontend restrictions are never authorization.

## Tenant isolation

- **Authorization chain:** authenticated user → correct account → correct workspace → role → allowed resource → allowed operation.
- **Horizontal boundaries:** test them by changing IDs, routes, bodies, query parameters and cached state.
- **Non-interactive paths:** background jobs, crons, webhooks, Pub/Sub and OAuth callbacks act only on the account/workspace proven by a trusted server-side record, never by a request parameter.

## Owner ↔ Users (both directions)

- **Users → Owner:** Users cannot reach Owner functionality by navigation or direct API. Owner routes enforce server-side role checks. Client-controlled values never grant Owner.
- **Owner → Users:** no Owner identity, account, contact, alias, card, configuration, heuristic or data may influence a User's processing. Shared code is neutral by default and gets its context from the caller's own account. A User's data must never be rewritten into another person's identity so that code "works".
- **The Owner as a user:** a normal feature uses the normal flow and isolation. There is no role bypass of entitlement, OAuth binding or tenancy.

Treat any violation as HIGH or BLOCKER.

## OAuth and mail providers (Gmail, Outlook)

- **Least privilege:** read-only scopes only (`gmail.readonly`, `Mail.Read`). Justify any scope change and never add write/send/delete scopes.
- **Flow binding:**
  - state stored server-side and single-use;
  - PKCE;
  - bound to provider, session, account and workspace;
  - expiry;
  - replay and duplicate-callback handling;
  - denial and error paths.
  A flow started by one account/workspace must never be completed by another.
- **Tokens:** refresh tokens are kept server-side in Supabase Vault, never sent to the app and never logged. Disconnect deletes and revokes; account deletion does too.
- **Mailboxes:** each mailbox is its own connection with its own secret, sync state and disconnect. Reconnecting A never overwrites B. The same movement from two mailboxes is one movement.
- **Retention:** store only what the feature needs. No raw email bodies or attachments beyond the review window. Derived review evidence and metadata follow the documented retention.
- **No AI:** data obtained from Google Workspace or Microsoft APIs, raw or derived, is never sent to a generative-AI provider and never used to train models.
- **No server-held personal mail tokens:** no mailbox is read through a globally configured token.
- **Test scenarios:**
  - normal return, duplicate callback, reload, restored tab;
  - warm, backgrounded and cold start, force-close;
  - network loss and retry, provider denial, expired flow;
  - wrong account or session.

## Supabase / database

- Inspect RLS, grants, service-role boundaries, SECURITY DEFINER, `search_path`, foreign keys and cascades.
- A table with RLS and no policies is not automatically a vulnerability if it is intentionally server-only.
- Never weaken RLS or authorization to make a feature work.

## Account deletion and export

- **Deletion is a full lifecycle:**
  - identity, dependent and legacy records, cascades;
  - external auth and Vault secrets, provider revocation;
  - partial failure, client cleanup;
  - login afterwards.
  It must not depend on the plan, so test every plan.
- **Export:** contains only the caller's data.

## Sensitive data, secrets and analytics

- **Sensitive data:** transactions, balances, income, debts, accounts, goals, and mail/PDF content. Check responses, logs, analytics, errors, local storage, caches and debug output.
- **Secrets:** never in bundles, source control, logs, analytics, screenshots, fixtures or errors. Never rotate or change production secrets without approval.
- **PostHog:** no names, emails, phones, real IDs, amounts, balances, debts, salaries, descriptions, mail content, OAuth data or free text. No autocapture or session recording without approval.

## Mobile QA

- **Layout:** narrow screens, safe areas, keyboard, scrolling, overflow, long Spanish/English strings, dialogs and sheets, touch targets. Never hide required content to fix overflow.
- **Lifecycle:** foreground ↔ background, terminated → cold start. Desktop assumptions fail on mobile.
- **Deep links:** app open, backgrounded or terminated; duplicate delivery; stale or malformed URLs; wrong scheme; intentionally supported legacy schemes. Handlers are idempotent.
- **Network:** slow, offline, disconnect mid-request, reconnect, retry, double submit. Retries must never duplicate financial records.

## Severity and evidence

- **Severity:**
  - BLOCKER: security, privacy or data loss, or a critical broken flow;
  - HIGH: serious regression or exploitable weakness;
  - MEDIUM: an important edge case;
  - LOW: hardening.
  Don't inflate severity.
- **Evidence:** distinguish discovered, reproduced, fixed, automated-tested and physically validated. Never claim device or production validation that didn't happen.
- **Scope:** outside-scope issues are documented, not fixed incidentally.
- **Production:** actions stay human-gated.
