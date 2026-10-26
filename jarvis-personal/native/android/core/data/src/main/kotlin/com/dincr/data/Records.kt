package com.dincr.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// JARVIS → Registros (Owner): the money timeline (`GET /finance/timeline`: the known incomes and
// obligations ahead and the balance they leave) and the account reconciliation
// (`GET /finance/reconciliation`: each tracked account's expected and real balance). Both reads
// never write; confirming a real balance is an explicit Owner command. Every amount is the
// backend's: one it did not send is unknown (null), never 0. iOS twin: `Records.swift`.

/** `GET /finance/timeline`. */
@Serializable
data class MoneyTimeline(
    @SerialName("start_date") val startDate: String? = null,
    @SerialName("end_date") val endDate: String? = null,
    @SerialName("opening_available") val openingAvailable: Money? = null,
    @SerialName("ending_available") val endingAvailable: Money? = null,
    val events: List<Event> = emptyList(),
    val assumptions: List<String> = emptyList(),
) {
    /** [kind]: `income`, `recurring_expense`, `debt_payment` or `goal` (a reminder that moves nothing). */
    @Serializable
    data class Event(
        val date: String? = null,
        val name: String? = null,
        val kind: String? = null,
        val amount: Money? = null,
        /** The change to the available balance (negative for an outflow; 0 for a reminder). */
        val impact: Money? = null,
        @SerialName("projected_balance") val projectedBalance: Money? = null,
        val note: String? = null,
    )

    /** The events grouped by day, in the backend's order. */
    val days: List<Pair<String, List<Event>>> get() = events.groupBy { it.date.orEmpty() }.toList()
}

/** `GET /finance/reconciliation`. */
@Serializable
data class Reconciliation(
    val accounts: List<Account> = emptyList(),
    val summary: Summary? = null,
    val note: String? = null,
) {
    @Serializable
    data class Account(
        @SerialName("account_id") val accountId: Long,
        @SerialName("account_name") val accountName: String? = null,
        val institution: String? = null,
        val last4: String? = null,
        val currency: String? = null,
        /** The last declared balance plus the movements recorded since. */
        @SerialName("expected_balance") val expectedBalance: Money? = null,
        /** The last declared (real) balance. */
        @SerialName("real_balance") val realBalance: Money? = null,
        val difference: Money? = null,
        @SerialName("movements_since_balance") val movementsSinceBalance: Int? = null,
        @SerialName("balance_as_of") val balanceAsOf: String? = null,
        val status: String? = null,
    ) {
        val needsReview: Boolean get() = status == "needs_review"
    }

    @Serializable
    data class Summary(
        val accounts: Int? = null,
        @SerialName("needs_review") val needsReview: Int? = null,
        val unlinked: Int? = null,
        @SerialName("possible_duplicates") val possibleDuplicates: Int? = null,
        @SerialName("untracked_accounts") val untrackedAccounts: Int? = null,
    )
}

/** `POST /finance/reconciliation/{account_id}/confirm`: the account's real balance today, as the Owner checked it. */
@Serializable
data class ReconciliationConfirmRequest(@SerialName("real_balance") val realBalance: Money, val note: String = "")

@Serializable
data class ReconciliationConfirmResult(val status: String? = null, val confirmed: Boolean? = null)
