# Email/PDF ingestion audit (Users)

## Flow

1. **Fetch.**
   - Gmail: `user_product/gmail_service.py` `_sync_connection` → `_process_message`.
   - Outlook: `user_product/microsoft_mail.py` `sync_connection`.
   - Both feed `_ingest_message`.
2. **Parser selection:** CCSS payroll order, then Banco Popular (`email_monitor/popular_pdf.py`), then `email_monitor/parser.py` `parse_financial_email`. `parse_financial_email` handles BAC purchase / SINPE / SINPE Móvil / card payment / statements, and MultiMoney.
3. **Candidate:** `financial_candidate.canonical_candidate` or `statement_candidate`, then `_insert_finva_candidate`, then `candidate_resolution.resolve_candidate` (semantic duplicates, own-account transfers).
4. **Review:** `review_gmail_candidate` accepts, corrects or rejects. An accepted candidate lands in `transactions`, which feeds Movimientos (`list_user_transactions`). Internal transfers are excluded.
5. **Idempotency:**
   - Re-sync is covered by `UNIQUE(connection_id, provider_message_id)`.
   - Double accept is covered by `FOR UPDATE` plus a status check.
   - The financial-input event uses `ON CONFLICT DO NOTHING`.

Supported, with synthetic tests:
- **BAC:** purchase, refund, SINPE, SINPE Móvil, card payment, account and card statements.
- **MultiMoney:** transfer and statement.
- **Banco Popular:** loan, SINPE, card-statement PDF.
- **CCSS:** payroll order.

**BN (Banco Nacional) has no parser.** Its emails stay `ignored`, and the new battery pins that behavior.

## Fixed in this PR

| Severity | Issue | Fix |
|---|---|---|
| HIGH | Amounts without decimals lost three orders of magnitude: `₡15.000` → 15, `CRC 1,234` → 1.23, `CRC 25000` → not parsed | One `AMOUNT_PATTERN` (thousands groups incl. space/NBSP, optional decimals, `(?!\d)`). `_parse_number` treats a single separator followed by 3 digits as thousands. Free-text searches try grouped/cents amounts first (`STRICT_AMOUNT_PATTERN`), so a count like "$ 3 por comisión" never beats "₡15.000,00" |
| HIGH | Amounts written as "dólares" were stored as colones (`_currency_code` compared uppercase text with a lowercased string) | Compare against the normalized lowercase `dolar` |
| MEDIUM | The fallback transaction date used the UTC day: a 19:30 purchase became "tomorrow" | `_local_date` converts to America/Costa_Rica. A date written in the email still wins |
| MEDIUM | Gmail matched bank senders by substring on the raw `From` header, so a forged display name (`"alerta@baccredomatic.com" <attacker@…>`) reached bank templates, including auto-saved paths | `bank_sender_allowed` requires exactly one address: the one inside `<…>` when present. A display name containing `@`, or a second sender, is rejected. The address must match an approved address/domain from `FINVA_QUERY`, the rule Outlook already enforced. **Check the production `FINVA_GMAIL_QUERY`:** the allowlist is derived from its `from:` terms, and a quoted or grouped override would silently ignore that bank. |
| MEDIUM | Two concurrent syncs of the same new message raised `IntegrityError` and aborted the whole sync | `ON CONFLICT DO NOTHING` plus `"duplicate"` |
| PRIVACY | The repository is **public**, and fixtures contained the Owner's real payroll data (full name, identification, salary, employer number) and statement references | Replaced with synthetic values. **Purging git history is a HUMAN GATE**: it needs a force-push/rewrite, or accepting the exposure |

Battery: `backend/email_monitor/test_parser_battery.py` (44 cases). 16 of them fail on the previous parser.

## Open findings (not changed: they need design or human decisions)

- **MEDIUM: a rejected movement can come back through another source.** `resolve_candidate` skips rejected rows. The same bank reference arriving via Outlook after the Gmail copy was rejected shows up again as pending.
- **MEDIUM: the same statement can be imported twice.** Gmail + Outlook or a re-sent statement are possible causes. `document_hash` is indexed but never checked, and statement rows without a reference have no semantic fingerprint.
- **MEDIUM: an accepted ambiguous `transfer` counts as neither income nor expense.** Totals only count income/expense types. The review UI should force a direction.
- **MEDIUM: Owner-specific heuristics live in the shared parser.**
  - The Owner's own IBAN/card environment variables (`JARVIS_OWN_*`) and family first names are hardcoded in `parser.py`. `_adapt_identity` also rewrites the user's display name to the Owner's name so those rules match.
  - Users' counterparties named like the Owner's family get normalized, and a user whose card last4 equals the Owner's gets "internal transfer" hints. Those hints only become reviewable transfers, never automatic decisions.
  - Moving them to per-workspace configuration is a refactor with Owner regression risk.
- **LOW:**
  - A message the sender gate rejects is stored as `ignored` and never retried, like every other ignored message.
  - The Owner pipeline (`email_monitor/service.py`) still detects banks by substring. It shares the amount fixes but not the Gmail sender gate.
  - USD is converted at a fixed rate of 495, and `transactions` stores no currency.
  - An `ignored` message is never re-parsed after a parser upgrade.
  - The Outlook `since` filter and `canonical_candidate` still use UTC dates.

## Missing samples (needed for the remaining coverage)

No real PDFs or `.eml` files are in the repo, and they must not be. To extend coverage safely, the Owner should provide **redacted** samples: names, full account/card numbers, references and amounts replaced, with the layout kept. The needed samples:
- BN: any purchase/SINPE notification and a monthly statement (needed to build a parser at all);
- BAC: a USD purchase, a card statement with USD rows, and a statement from a different month/year;
- Banco Popular: a debit-account statement PDF;
- MultiMoney: a monthly statement PDF;
- an email/PDF that failed to parse in production (`email_parser_logs` / `finva_parser_fallback_events`), to seed the unknown-format flow.
