package com.dincr.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * `GET /user-product/finance/expenses/pending-conversion`: the expenses typed in dollars that wait for
 * the close (the card's statement cut, or the calendar month without a card) to be converted with one
 * rate, and their totals per currency. They have no colones amount yet: the colones lists and totals
 * leave them out, and the app shows them apart, never as ₡0. [available] is false while the server
 * can't keep an expense pending yet: the editor then always asks for the rate. iOS: `PendingConversion`.
 */
@Serializable
data class PendingConversion(
    val available: Boolean = false,
    val items: List<Item> = emptyList(),
    val totals: List<Total> = emptyList(),
    /** The closes the waiting expenses belong to (3d), oldest first; empty from a server without the close. */
    val periods: List<Period> = emptyList(),
) {
    @Serializable
    data class Item(
        @SerialName("movement_id") val movementId: String,
        val id: Long,
        @SerialName("entry_date") val entryDate: String,
        val description: String = "",
        val category: String? = null,
        @SerialName("original_amount") val originalAmount: Money,
        @SerialName("original_currency") val originalCurrency: String,
        @SerialName("financial_account_id") val financialAccountId: Long? = null,
        /** The close it belongs to ([Period.key]); null from a server without the close. */
        @SerialName("period_key") val periodKey: String? = null,
    ) {
        /** The expense as the editor opens it: in its own currency, still waiting for the close. */
        val movement: Movement
            get() = Movement(
                movementId = movementId, sourceId = id, origin = "expense", transactionDate = entryDate, description = description,
                amount = originalAmount, transactionType = "expense", category = category, editable = true,
                originalAmount = originalAmount, originalCurrency = originalCurrency, financialAccountId = financialAccountId,
            )
    }

    @Serializable
    data class Total(val currency: String, val amount: Money, val count: Int)

    /**
     * One close: a card's statement cycle, or a calendar month without a card. It converts once it has
     * ended ([closable]). A card without a declared cut day falls in its month ([cutDayMissing]).
     */
    @Serializable
    data class Period(
        val key: String,
        val kind: String,
        val start: String,
        val end: String,
        val closable: Boolean = false,
        @SerialName("cut_day_missing") val cutDayMissing: Boolean = false,
        @SerialName("account_id") val accountId: Long? = null,
        @SerialName("account_name") val accountName: String? = null,
        @SerialName("account_last4") val accountLast4: String? = null,
        val totals: List<Total> = emptyList(),
        val count: Int = 0,
    ) {
        val isCard: Boolean get() = kind == "card"
    }

    companion object {
        val UNAVAILABLE = PendingConversion()
    }
}

/** Body of `POST /user-product/finance/expenses/pending-conversion/close`: one rate for one close. */
@Serializable
data class PendingClose(@SerialName("period_key") val periodKey: String, @SerialName("exchange_rate") val exchangeRate: Money)

/** What a close converted: how many expenses and their total in the base currency. */
@Serializable
data class PendingCloseResult(val converted: Int = 0, val amount: Money, val currency: String, @SerialName("exchange_rate") val exchangeRate: Money)
