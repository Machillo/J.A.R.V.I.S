package com.dincr.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// JARVIS "Control de dinero": the Owner's cuentas por cobrar (the historical web Receivables page).
// `GET /finance/receivables/view` (owner/admin on the server; the app shows the section only for the
// Owner role): the same list and figures as the web's `GET /finance/receivables`, read only (no sync,
// nothing stored). Every figure is the backend's; a missing number is unknown (null), never zero.
// iOS twin: `ReceivableModels.swift`.

/** `GET /finance/receivables/view`. */
@Serializable
data class ReceivablesReport(
    val cycle: Cycle? = null,
    val items: List<Receivable> = emptyList(),
    val summary: Summary? = null,
) {
    @Serializable
    data class Cycle(val start: String? = null, val end: String? = null)

    @Serializable
    data class Summary(
        @SerialName("total_pending") val totalPending: Money? = null,
        @SerialName("carried_pending") val carriedPending: Money? = null,
        @SerialName("cycle_charges") val cycleCharges: Money? = null,
        @SerialName("cycle_payments") val cyclePayments: Money? = null,
        @SerialName("count_open") val countOpen: Int? = null,
        @SerialName("people_count") val peopleCount: Int? = null,
    )
}

/** One person who owes the Owner money, with the current card cycle's figures. */
@Serializable
data class Receivable(
    val id: Long,
    @SerialName("person_name") val personName: String? = null,
    /** "pending", "partial", "completed" or "credit" (the person paid more than owed). */
    val status: String? = null,
    @SerialName("current_amount_due") val currentAmountDue: Money? = null,
    @SerialName("carried_pending") val carriedPending: Money? = null,
    @SerialName("cycle_charges") val cycleCharges: Money? = null,
    @SerialName("cycle_payments") val cyclePayments: Money? = null,
    val notes: String? = null,
    @SerialName("is_auto") val isAuto: Boolean? = null,
    val history: List<Entry> = emptyList(),
) {
    @Serializable
    data class Entry(
        val id: Long,
        /** "charge" (lent or charged) or "payment" (received). */
        @SerialName("entry_type") val entryType: String? = null,
        val amount: Money? = null,
        val description: String? = null,
        @SerialName("entry_date") val entryDate: String? = null,
    ) {
        val isPayment: Boolean get() = entryType == "payment"
    }
}
