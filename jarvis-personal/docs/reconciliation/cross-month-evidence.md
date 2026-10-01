# Cross-month evidence in historical reconstruction

A movement's date, the cycle of the statement that lists it and the day that statement arrives are
three different things:

    transaction date  ≠  statement cycle  ≠  statement arrival date

A card statement named after a month (for example "202602") covers a cycle with its own cutoff
(for example 21 January – 20 February) and arrives days later. It can list movements of the
previous month; it never moves them into its own month.

## Rules

1. **Economic month.** A movement belongs to the month of its own date. Neither the statement's
   name, its cycle nor its arrival date changes that.
2. **Pending, not guessed.** A movement the evidence cannot decide is closed as
   `pending_reconciliation`. It is not written as income, refund or own transfer, it is never
   turned into zero, and it does not block closing its month.
3. **Later evidence.** Each later month's statements and notices are checked against the pending
   movements of earlier months. When the new evidence is sufficient:
   1. identify the historical movement — the same row, never a duplicate;
   2. record what settled it: document, line, cycle and arrival date
      (`reconciliation.resolution` in `staging_manifest.schema.json`);
   3. reclassify only that row and keep its economic date;
   4. recalculate the totals of its economic month.
4. **Insufficient evidence keeps it pending.** Never pair movements by amount alone: a match needs
   reference, account, date and amount together, or another explicit signal.

These rules are bank-neutral: they describe documents with cycles and arrival dates, not any one
institution's layout.
