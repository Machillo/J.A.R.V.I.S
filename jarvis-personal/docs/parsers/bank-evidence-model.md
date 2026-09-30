# Bank notices: evidence model (BAC, MultiMoney)

What real BAC and MultiMoney notices contain, and how the parser reads them. It
was built from a read-only study of real notices, then validated against real
messages without storing them. Every example in the tests is synthetic
(`backend/email_monitor/test_bank_evidence_formats.py`,
`backend/user_product/test_sinpe_reference_correlation.py`).

## Senders

BAC moves the same templates between sender addresses. Classification is
therefore driven by the body template, and the fetch list must follow the
senders:

| Notice | Senders (oldest → newest) |
|---|---|
| Card alert ("Notificación de transacción") | `notificacion@notificacionesbaccr.com` → `notificacion@baccredomatic.cr` → `NotificacionBAC@baccredomatic.cr` |
| SINPE ("Notificación de Transferencia") | `sinpe@notificacionesbaccr.com` → `notificaciones@baccredomatic.cr` |
| Card payment, service payment, cardless withdrawal | `alerta@baccredomatic.com` |
| MultiMoney transfers, credits, payments | `multimoneycr@multimoney.com` |

A single list feeds three places: `FINVA_QUERY` (Gmail), `bank_sender_allowed`
(Gmail's From check) and the Outlook allowlist. `parser.BANK_SENDERS` holds the
same addresses. Senders without money-movement evidence stay out: declines,
installment reminders, sign-in alerts, marketing, e-invoices and Wise.

## Bank movement ≠ financial effect

One notice describes a **bank movement**. Its **financial effect** often needs
the other side, so the parser writes both to the candidate's `raw_payload`
(`bank_movement`, `financial_effect`; see `email_monitor/movement_taxonomy.py`):

| Bank movement | Candidate | Effect |
|---|---|---|
| Card `COMPRA` / `CARGO AUTOMATICO` | expense | expense |
| Card `DEVOLUCION` | transfer in, kind `refund` | refund: never ordinary income |
| Card `PAGO` (e.g. RED PUNTOS) | transfer in, kind `reward` | reward: never an expense |
| Card `.00` authorization | ignored | none |
| SINPE credit / debit | transfer in / out | review: the notice never names the other party |
| SINPE rejected | ignored | none |
| MultiMoney transfer | transfer, direction from the holder's side | review |
| MultiMoney `INVERSIÓN VISTA SMART COL` | transfer in | own transfer likely |
| MultiMoney same-holder `cambio` (CRC→USD) | transfer | own FX move likely |
| MultiMoney real-time debit ("Débito aplicado por otra entidad financiera") | transfer out | review (in practice, the holder pulling money into another bank) |
| MultiMoney "¡Te hemos acreditado!" / "Depositamos tu crédito" | transfer in, kind `loan_disbursement` | liability: debt, never income |
| MultiMoney "Recibimos tu pago." | debt_payment | debt payment |
| BAC "Comprobante de Pago de Tarjeta" | transfer out, kind `card_payment` | own transfer likely (account → own card) |
| BAC cardless withdrawal (withdrawn) | transfer out, kind `cash_withdrawal` | cash; the code-creation notice moves nothing |
| BAC service payment | expense | expense |

A transfer is never counted as income or spending by default. The user
confirms, corrects or dismisses it. The one exception is a credit carrying
explicit payroll words, which stays income (`payroll_income.py`).

An additional card on the holder's account greets its own cardholder. That
charge is still billed to the holder, so it stays an expense, flagged
`cardholder_mismatch` with a lower confidence.

## Correlation (own-account transfers)

- **Strong key:** one SINPE transfer carries the same 25-digit reference in both
  banks' notices, for example a BAC credit and a MultiMoney real-time debit.
  Pairing needs all of the following:
  - the same reference;
  - the same amount in the movement's own currency (USD is never compared with CRC);
  - opposite directions.
- **Negative evidence:** two different SINPE references are two transfers,
  whatever the amount and time.
- **Automatic** internal marking still requires both endpoints to be accounts the
  user confirmed as their own. Otherwise the pair is a suggestion, and
  reference-backed pairs are listed first. Nothing pairs on amount alone.
- The meaning of the reference's internal segments is not used.

## Deduplication

- Every template now emits `reference`, which fills
  `finva_email_candidates.external_reference`. The semantic fingerprint uses it,
  so two copies of one notice (resent email, Gmail plus Outlook) are one movement.
- Charges with different references stay distinct.
- References by notice:
  - card alerts: `Referencia` (or `Autorización`);
  - SINPE and MultiMoney: the 25-digit reference;
  - MultiMoney loan payment: promissory note plus date and time;
  - card payment: its short reference plus the payment time, because BAC reuses the short reference.
- Notices without a reference keep the existing time + account + description
  fingerprint, or none.

## Clocks and formats

- **Card dates:** `Sep 30, 2026, 02:13`, `Sep 23, 2026 , 13:32` and `Sep 21,2026 , 00:00`.
- **SINPE:** 12-hour times with `a.m.`/`p.m.`.
- **MultiMoney time zone:** MultiMoney printed UTC for a period. A printed time
  is read as UTC only when it matches the email's own UTC timestamp and not its
  Costa Rica time.
- **Accounts:** only the last four digits are kept, even when a notice prints a
  full IBAN or account number.

## Not supported (on purpose)

- **Wise:** FX top-ups and transfers that later arrive as SINPE credits. No
  deterministic parser yet. It is a candidate for future unknown-format
  handling. Any runtime AI for that would need an explicit change to the
  product's no-generative-AI rule for user data.
- **Other international institutions:** not supported.
- **Statement PDF contents and e-invoices:** not handled in this change.
