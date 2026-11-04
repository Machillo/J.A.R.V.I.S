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
    /** The server converts them by itself at the close, with the dollar of that day. False: the app promises nothing. */
    @SerialName("auto_close") val autoClose: Boolean = false,
) {
    /** What the waiting dollars on screen add to the expenses: with a search every month, without one only [month]. */
    fun estimate(month: String, query: String): PendingEstimate {
        val shown = items.filter { (query.isNotBlank() || it.entryDate.startsWith(month)) && SearchText.matches(query, listOf(it.description, it.category)) }
        val known = shown.mapNotNull { it.estimatedAmount }
        return PendingEstimate(if (known.isEmpty()) null else known.fold(java.math.BigDecimal.ZERO) { sum, value -> sum + value }, shown.size - known.size)
    }

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
        /** In the base currency at the purchase day's rate, only to follow what is owed; null: unknown. The final amount comes at the close. */
        @SerialName("estimated_amount") val estimatedAmount: Money? = null,
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
    data class Total(
        val currency: String,
        val amount: Money,
        val count: Int,
        /** Left out by the server when one of its expenses has no estimate: never a partial sum. */
        @SerialName("estimated_amount") val estimatedAmount: Money? = null,
    )

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

/** [sum] null: none on screen has an estimate. [withoutEstimate]: named on screen, not counted as 0. */
data class PendingEstimate(val sum: java.math.BigDecimal?, val withoutEstimate: Int)

/** Body of `POST /user-product/finance/expenses/pending-conversion/close`: one rate for one close. */
@Serializable
data class PendingClose(@SerialName("period_key") val periodKey: String, @SerialName("exchange_rate") val exchangeRate: Money)

/** What a close converted: how many expenses and their total in the base currency. */
@Serializable
data class PendingCloseResult(val converted: Int = 0, val amount: Money, val currency: String, @SerialName("exchange_rate") val exchangeRate: Money)
