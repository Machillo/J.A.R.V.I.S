---
name: dincr-data-integrity
description: Checklist for any DINCR change that reads, writes, imports, parses, reconciles or displays financial data (transactions, debts, balances, income, goals, strategy, mail candidates). Use before implementing and again when reviewing such a change, including read-only screens, background jobs, parsers and mail ingestion.
---

# DINCR Data Integrity

Run this checklist for every change that touches financial data. Answer each question with evidence from the code (a path or a test), not from intent. A "don't know" is a finding.

## 1. Read or command?

- Is this path a **read** (GET, dashboard, report, strategy, preview, projection, notification rendering) or a **command** (explicit user or authorized automation action)?
- If read: can it write **directly or indirectly**? Follow every helper it calls. Look for `INSERT`, `UPDATE`, `DELETE`, automatic payment and installment syncs, "auto-apply", "sync", "ensure", "backfill", "reconcile" helpers.
- A read must not:
  - reduce or change debts;
  - create payments or transactions;
  - change balances;
  - advance goals;
  - alter any user financial record.
  If an automation must write, it is a command with explicit authorization and scope (which accounts opted in), not a side effect of opening a screen.
- Schema DDL during reads (`ensure_*`, `CREATE TABLE IF NOT EXISTS`) is legacy. Do not add it; schema belongs in migrations.
- **Guard:** `backend/tests/test_read_surfaces_are_read_only.py` runs Users read surfaces against a connection that fails on financial writes. Add new read surfaces there.

## 2. Whose data?

- Which `account_id` and `workspace_id` does every query use, and where do they come from (authenticated session, stored flow or connection row)? A client-supplied ID must not cross workspaces.
- What happens with **two users**? With the same user in **two workspaces**?
- What happens with the **Owner**? Owner data, configuration, heuristics or engines must not shape a User's result, and the Owner must not bypass the normal isolation when using a normal feature.
- Background jobs, crons, webhooks and callbacks: which account/workspace do they act on, and how is that proven without a session?

## 3. Values and precedence

- Did an **unknown become zero** (null balance, missing income, unscanned month)?
- Does imported, discovered or partial data **replace a declared value**? If a reconciliation is needed, is there an explicit versioned policy (`dincr-finance` → `references/data-precedence.md`) and is it the same one every screen uses?
- **Double counting:** declared plus observed, recurring plus declared, a notification plus a statement.
- **Internal transfers:** are both endpoints proven to be the user's **own** accounts from their workspace? Never infer it from someone else's configuration.

## 4. Repetition and concurrency

- **Idempotent?** Retry, double submit, re-import, re-parse, reconnecting a mailbox, a duplicate Pub/Sub or deep-link delivery.
- **Two mailboxes** or providers (Gmail + Outlook) seeing the same movement: is it one movement?
- **Concurrent runs** (push + manual sync, two devices): row locks, unique keys, `ON CONFLICT`.
- **Partial failure** halfway: what is left behind, and is the operation transactional?

## 5. Partial and legacy data

- What happens with partial data (a first sync of only one month, a statement without some rows)?
- What happens with **existing** production rows created by older code? Never delete or rewrite user financial data as part of a fix. Report affected data and give a read-only query, and leave the correction to a human.

## 6. Parsers and shared ingestion

- Is the parser **neutral by default**, and does it get the holder's identity and accounts only from the caller's own account/workspace?
- No hardcoded personal names, contacts, accounts or cards. No Owner env configuration outside Owner-only paths.
- Raw email bodies and attachments are not stored beyond what the feature needs. Fixtures are synthetic.

## 7. Evidence to attach

- A regression test that **fails without the change**, with the failing run shown (old code or a mutation).
- Tests with **two synthetic users** (and the Owner when relevant) proving isolation.
- The full backend suite result.
- Any production data already affected, as a read-only query for human review.
