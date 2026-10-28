package com.dincr.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// JARVIS → Control de dinero (Owner): the money other people owe the Owner ("cuentas por cobrar"),
// by card cycle (it closes on day 21). Read from `GET /finance/receivables`, which never writes;
// a payment or a new charge is an explicit Owner command. Every amount is the backend's: an amount
// it did not send is unknown (null), never 0, and a negative amount due is the person's credit.
// iOS twin: `Receivables.swift`.

/** `GET /finance/receivables`. */
@Serializable
data class ReceivablesReport(
    val cycle: Cycle? = null,
    val items: List<Receivable> = emptyList(),
    val summary: Summary? = null,
) {
    @Serializable data class Cycle(val start: String? = null, val end: String? = null)

    @Serializable
    data class Summary(
        @SerialName("total_pending") val totalPending: Money? = null,
        @SerialName("count_open") val countOpen: Int? = null,
        @SerialName("people_count") val peopleCount: Int? = null,
    )
}

/** One person who owes the Owner money, for the current card cycle. */
@Serializable
data class Receivable(
    val id: Long,
    @SerialName("person_name") val personName: String? = null,
    /** What the person owes now (carried + this cycle's charges − payments). Negative: credit. */
    @SerialName("current_amount_due") val currentAmountDue: Money? = null,
    @SerialName("carried_pending") val carriedPending: Money? = null,
    @SerialName("cycle_charges") val cycleCharges: Money? = null,
    @SerialName("cycle_payments") val cyclePayments: Money? = null,
    @SerialName("status") val statusWire: String? = null,
    /** Charges that came from an additional card (`additional_card_auto`). */
    @SerialName("is_auto") val isAuto: Boolean = false,
    val history: List<ReceivableEntry> = emptyList(),
) {
    enum class Status { PENDING, PARTIAL, COMPLETED, CREDIT, UNKNOWN }

    val status: Status get() = when (statusWire) {
        "pending" -> Status.PENDING
        "partial" -> Status.PARTIAL
        "completed" -> Status.COMPLETED
        "credit" -> Status.CREDIT
        else -> Status.UNKNOWN
    }

    /** Whether a payment can be recorded: only while the person owes something. */
    val canRecordPayment: Boolean get() = (currentAmountDue?.signum() ?: 0) > 0
}

/** A charge (they owe more) or a payment (they paid), as the backend recorded it. Amounts are positive. */
@Serializable
data class ReceivableEntry(
    val id: Long,
    @SerialName("entry_type") val entryType: String? = null,
    val amount: Money? = null,
    val description: String? = null,
    @SerialName("entry_date") val entryDate: String? = null,
    @SerialName("source_type") val sourceType: String? = null,
) {
    val isPayment: Boolean get() = entryType == "payment"
}

/** `POST /finance/receivables/{id}/payments`: a payment the person made (cash by default). */
@Serializable
data class ReceivablePaymentRequest(
    val amount: Money,
    val notes: String = "",
    @SerialName("payment_date") val paymentDate: String? = null,
)

/** `POST /finance/receivables/entries`: money someone now owes the Owner. */
@Serializable
data class ReceivableEntryRequest(
    @SerialName("person_name") val personName: String,
    val amount: Money,
    val description: String = "",
    @SerialName("entry_kind") val entryKind: String = "purchase",
) {
    companion object {
        /** The kinds the backend knows (receivable_semantics.py); anything else is stored as "other". */
        val kinds = listOf("purchase", "loan", "transfer", "cash", "other")
    }
}

/** The answer of both writes: the backend reports a refused write in the body (`status`), not with an HTTP error. */
@Serializable
data class ReceivableWriteResult(val status: String? = null, val message: String? = null) {
    val succeeded: Boolean get() = status == "OK"
}

// Cards billed to the Owner but carried by someone else: a purchase notice on one of them is that
// person's debt (the backend settles it into their receivable), not the Owner's expense. Read from
// `GET /finance/additional-cards`, which never writes; marking or unmarking is an explicit command.
// iOS twin: `AdditionalCards.swift`.

/** One card the Owner marked as carried by a person. */
@Serializable
data class AdditionalCard(
    @SerialName("card_last4") val cardLast4: String = "",
    @SerialName("person_name") val personName: String? = null,
)

/** `GET /finance/additional-cards`. A row without a card is not a card. */
@Serializable
data class AdditionalCards(@SerialName("items") val raw: List<AdditionalCard> = emptyList()) {
    val items: List<AdditionalCard> get() = raw.filter { it.cardLast4.isNotEmpty() }
}

/** `PUT /finance/additional-cards/{last4}`: who carries the card. */
@Serializable
data class AdditionalCardRequest(@SerialName("person_name") val personName: String) {
    companion object {
        /** The last 4 digits the backend accepts: exactly four ASCII digits, nothing else. */
        fun last4(text: String): String? = text.trim().takeIf { t -> t.length == 4 && t.all { it in '0'..'9' } }
    }
}

/** The answer of marking (`settled_purchases`) or unmarking (`released_purchases`) a card. */
@Serializable
data class AdditionalCardResult(
    val status: String? = null,
    @SerialName("settled_purchases") val settledPurchases: Int? = null,
    @SerialName("released_purchases") val releasedPurchases: Int? = null,
)
