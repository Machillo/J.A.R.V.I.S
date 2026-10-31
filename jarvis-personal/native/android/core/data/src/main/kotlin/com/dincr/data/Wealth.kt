package com.dincr.data

import java.math.BigDecimal
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// WE-2 — Patrimonio (VIP and the Owner): what you have and what you owe
// (`GET /user-product/vip/wealth`). The backend counts every part; net worth is null while any part
// is unknown (named in `unknown`), never computed as if it were 0. iOS twin: `WealthModels.swift`.

@Serializable
data class Wealth(
    val assets: Assets? = null,
    val liabilities: Liabilities? = null,
    @SerialName("net_worth") val netWorth: Money? = null,
    val complete: Boolean? = null,
    val unknown: List<String> = emptyList(),
) {
    @Serializable
    data class Item(
        val name: String? = null,
        val amount: Money? = null,
        val currency: String? = null,
        @SerialName("original_amount") val originalAmount: Money? = null,
    )

    @Serializable
    data class Assets(val accounts: List<Item> = emptyList(), val salvavidas: Item? = null, val investments: List<Item> = emptyList(), val total: Money? = null)

    @Serializable
    data class Liabilities(val debts: List<Item> = emptyList(), val accounts: List<Item> = emptyList(), val total: Money? = null)

    /** What you have, in the order the screen lists it: accounts, the Salvavidas, investments. */
    val owned: List<Item> get() = (assets?.accounts ?: emptyList()) + listOfNotNull(assets?.salvavidas) + (assets?.investments ?: emptyList())

    /** What you owe: the debts (one line with their total) and any overdrawn account. */
    fun owed(language: AppLanguage = AppLanguage.current()): List<Item> {
        val debts = liabilities?.debts ?: emptyList()
        val total = if (debts.any { it.amount == null }) null else debts.fold(BigDecimal.ZERO) { sum, item -> sum + item.amount!! }
        val line = if (debts.isEmpty()) emptyList() else listOf(Item(language.pick("Deudas", "Debts"), total))
        return line + (liabilities?.accounts ?: emptyList())
    }

    /** "Falta el saldo de: X, Y." when net worth cannot be known yet; null when it is complete. */
    fun missingNotice(language: AppLanguage = AppLanguage.current()): String? {
        if (unknown.isEmpty()) return null
        val names = unknown.joinToString(", ")
        return language.pick("Falta el saldo de: $names. Cuando lo tengamos, te mostramos tu patrimonio neto.",
            "Missing the balance of: $names. Once we have it, we show your net worth.")
    }
}
