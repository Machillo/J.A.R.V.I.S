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

    companion object {
        val UNAVAILABLE = PendingConversion()
    }
}
