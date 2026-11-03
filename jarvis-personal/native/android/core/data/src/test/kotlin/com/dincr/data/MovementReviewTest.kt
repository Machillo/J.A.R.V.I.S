package com.dincr.data

import java.math.BigDecimal
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class MovementReviewTest {
    @Test fun everydayAmountsSaveDirectly() {
        assertFalse(MovementReview.isNeeded(BigDecimal("18450"), "CRC", convertsNow = false))
        assertFalse(MovementReview.isNeeded(BigDecimal("499999.99"), "CRC", convertsNow = false))
        assertFalse(MovementReview.isNeeded(BigDecimal("999.99"), "USD", convertsNow = false))
    }

    @Test fun largeAmountsAndConversionsGetAReview() {
        assertTrue(MovementReview.isNeeded(BigDecimal("500000"), "CRC", convertsNow = false))
        assertTrue(MovementReview.isNeeded(BigDecimal("1000"), "usd", convertsNow = false))
        assertTrue(MovementReview.isNeeded(BigDecimal("5"), "USD", convertsNow = true))
    }

    @Test fun anUnknownCurrencyIsNotALargeAmount() {
        assertFalse(MovementReview.isNeeded(BigDecimal("9000000"), "EUR", convertsNow = false))
    }
}
