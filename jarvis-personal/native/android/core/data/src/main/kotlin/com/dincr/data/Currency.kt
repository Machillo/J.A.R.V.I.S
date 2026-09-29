package com.dincr.data

import java.math.BigDecimal
import java.math.RoundingMode

/**
 * The base-currency amount the backend will store for an amount typed in another currency, for a
 * preview only (the backend computes and stores the real value). Same arithmetic as
 * `user_product/entry_currency.resolve_entry_amount`: the typed amount rounded to cents, the rate
 * (colones per 1 dollar) to 6 decimals, dollars → colones multiply, colones → dollars divide,
 * half-up to cents.
 */
object ConversionPreview {
    fun baseAmount(typed: BigDecimal?, currency: String, base: String, rate: BigDecimal?): BigDecimal? {
        if (typed == null || rate == null || rate.signum() <= 0) return null
        val code = currency.uppercase()
        val baseCode = base.uppercase()
        if (code == baseCode) return typed.setScale(2, RoundingMode.HALF_UP)
        val amount = typed.setScale(2, RoundingMode.HALF_UP)
        val r = rate.setScale(6, RoundingMode.HALF_UP)
        if (r.signum() <= 0) return null
        val converted = when {
            code == "USD" && baseCode == "CRC" -> amount.multiply(r)
            code == "CRC" && baseCode == "USD" -> amount.divide(r, 10, RoundingMode.HALF_UP)
            else -> return null
        }
        return converted.setScale(2, RoundingMode.HALF_UP).takeIf { it.signum() > 0 }
    }

    /**
     * The rate the user typed most recently on a manual entry, to prefill the next one (the user
     * can change it). Never a market rate: DINCR does not look rates up.
     */
    fun latestUserRate(movements: List<Movement>): BigDecimal? =
        movements.filter { it.origin == "salary" || it.origin == "expense" }
            .filter { it.exchangeRate != null && it.exchangeRate.signum() > 0 }
            .maxWithOrNull(compareBy<Movement> { it.transactionDate.orEmpty() }.thenBy { it.sourceId ?: 0 })?.exchangeRate
}
