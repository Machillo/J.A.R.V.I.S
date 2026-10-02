# Account balances: cash effect of each movement

A declared account balance moves only by the **cash effect** of the movements linked to that
account after the declaration (`backend/finance/balance_movements.py`). The cash effect is a
different axis from the economic classification:

| Type | Economic classification | Cash effect on its account |
|---|---|---|
| `income` | income | + |
| `refund`, `reimbursement` | reverses spending / neutral | + |
| `receivable_payment` | collection, not income | + |
| `asset_sale` | sale of something owned, not income | + |
| `loan_received`, `loan_disbursement` | liability proceeds, **never income** | + |
| `expense` | spending | − |
| `debt_payment` | debt payment | − |
| `receivable_offset` | settled without cash | 0 |
| `internal_transfer`, `transfer` (own transfers, card payments) | neutral | 0 (see below) |

Income, spending, cash-flow reports and strategy classify movements on their own. The balance
engine never decides that something is income, and it never creates or changes a debt: a
loan's liability is a `debts` row, so net worth gains the cash and the debt together.

## Architectural debt: transfers between accounts

An own transfer, or a card payment, is one `transactions` row with a single
`financial_account_id`; its origin and destination exist only as text in `account`
(`"BAC ****8137 + MM ****6126"`, `"… → …"`). A correct per-account balance needs the
transfer to take cash out of the origin and put it into the destination, and a card payment
to lower the bank balance and the card's debt. With one linked account and no direction,
neither side can be applied, so transfers stay neutral here and a balance that has transfers
after its declaration is understated or overstated by their net.

Fixing it needs an explicit model, for example one row per account side with its sign, or a
counter-account plus direction, and a decision on how history is represented. That is a
separate change with its own data and migration review; until then, declare the account
balance again after transfers to keep it accurate.
