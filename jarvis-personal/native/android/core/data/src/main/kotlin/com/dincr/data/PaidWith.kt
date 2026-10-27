package com.dincr.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * `GET /user-product/finance/expenses/paid-with-options`: the user's own active accounts and cards an
 * expense can say it was paid with (cards first). [available] is false while the server does not
 * store the link yet: the editor then hides "Pagado con". iOS: `PaidWithOptions`.
 */
@Serializable
data class PaidWithOptions(val available: Boolean = false, val items: List<Option> = emptyList()) {
    @Serializable
    data class Option(
        val id: Long,
        @SerialName("account_name") val accountName: String? = null,
        @SerialName("bank_name") val bankName: String? = null,
        @SerialName("account_type") val accountType: String? = null,
        @SerialName("account_last4") val accountLast4: String? = null,
        val currency: String? = null,
    ) {
        val isCard: Boolean get() = accountType == "credit_card"

        /** "BAC · Tarjeta de crédito ••5678" — what the user named, never more than the last 4 digits. */
        val label: String get() = listOfNotNull(bankName?.takeIf { it.isNotEmpty() },
            listOfNotNull(accountName, accountLast4?.takeIf { it.isNotEmpty() }?.let { "••$it" }).joinToString(" ").takeIf { it.isNotEmpty() })
            .joinToString(" · ")
    }

    /** What the editor offers: nothing while unavailable or without own accounts. */
    val offered: List<Option> get() = if (available) items else emptyList()
}

/**
 * The "paid with" part of an edit: an older screen leaves the link as it is (the key is not sent);
 * the editor that shows the picker sends the choice, `null` clearing it. iOS: `PaidWithChange`.
 */
sealed interface PaidWithChange {
    data object Unchanged : PaidWithChange
    data class Set(val accountId: Long?) : PaidWithChange
}
