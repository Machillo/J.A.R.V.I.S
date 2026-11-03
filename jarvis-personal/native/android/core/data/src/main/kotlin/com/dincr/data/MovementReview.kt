package com.dincr.data

import java.math.BigDecimal

/**
 * Whether a new movement gets a review before saving: only where a slip costs more, so everyday
 * expenses save directly. Presentation only: it never changes what is saved. iOS: `MovementReview`.
 */
object MovementReview {
    /** From here an amount is unusual enough to read twice. Other currencies never reach the entry today. */
    private val LARGE_AMOUNT = mapOf("CRC" to BigDecimal(500_000), "USD" to BigDecimal(1_000))

    /** [convertsNow]: typed in another currency and converted with a rate the user typed. */
    fun isNeeded(amount: BigDecimal, currency: String, convertsNow: Boolean): Boolean {
        if (convertsNow) return true
        val large = LARGE_AMOUNT[currency.uppercase()] ?: return false
        return amount >= large
    }
}
