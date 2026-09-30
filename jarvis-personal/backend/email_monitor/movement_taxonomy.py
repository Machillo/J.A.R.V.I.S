"""What a bank email says happened, kept apart from what it means financially.

A bank notice describes a *bank movement* (money left or entered an account or
card). Its *financial effect* (spending, income, own money moving between
pockets, a loan) often cannot be decided from one email: a SINPE credit may be
a salary, a refund or the holder pulling their own money from another bank.
The parser records the movement exactly and states the effect only when the
email itself proves it; everything else stays ``review`` for
Confirm/Correct/Dismiss or for a deterministic correlation with the other
side's notice (``user_product/candidate_resolution.py``).

Values are written to the candidate's raw_payload (``bank_movement``,
``financial_effect``); ``movement_kind`` keeps its existing column meaning.
"""
from __future__ import annotations

# Bank movements observed in real BAC / MultiMoney notices.
CARD_PURCHASE = "card_purchase"
CARD_AUTOMATIC_CHARGE = "card_automatic_charge"
CARD_REFUND = "card_refund"
CARD_POINTS_CREDIT = "card_points_credit"
CARD_CREDIT = "card_credit"
CARD_PAYMENT = "card_payment"
SERVICE_PAYMENT = "service_payment"
CASH_WITHDRAWAL = "cash_withdrawal"
SINPE_OUT = "sinpe_out"
SINPE_IN = "sinpe_in"
TRANSFER_OUT = "transfer_out"
TRANSFER_IN = "transfer_in"
TRANSFER_UNKNOWN = "transfer_unknown"
REALTIME_DEBIT = "realtime_debit"
OWN_ACCOUNT_FUNDING = "own_account_funding"
OWN_ACCOUNT_TRANSFER = "own_account_transfer"
FX_CONVERSION = "fx_conversion"
LOAN_DISBURSEMENT = "loan_disbursement"
LOAN_PAYMENT = "loan_payment"

# Financial effects. Only EXPENSE and DEBT_PAYMENT are decided by the email alone;
# the rest never count as ordinary income or spending without the user.
EXPENSE = "expense"
REFUND = "refund"                # reduces spending; never ordinary income
REWARD = "reward"                # points / cashback credit; never spending
OWN_TRANSFER_LIKELY = "own_transfer_likely"  # the email says so; ownership still needs confirmation
LIABILITY = "liability"          # loan proceeds: debt, not income
DEBT_PAYMENT = "debt_payment"
CASH = "cash"                    # own money moved to cash
REVIEW = "review"                # cannot be decided from this email

# movement_kind values for kinds that are not a plain transfer or purchase.
KIND_REFUND = "refund"
KIND_REWARD = "reward"
KIND_CARD_PAYMENT = "card_payment"
KIND_LOAN_DISBURSEMENT = "loan_disbursement"
KIND_CASH_WITHDRAWAL = "cash_withdrawal"
# Kinds tied to a card number: a signal for a credit-card account.
CARD_KINDS = frozenset({"card_purchase", KIND_REFUND, KIND_REWARD})


def movement(bank_movement: str, effect: str, kind: str | None = None) -> dict[str, str]:
    fields = {"bank_movement": bank_movement, "financial_effect": effect}
    if kind:
        fields["movement_kind"] = kind
    return fields
