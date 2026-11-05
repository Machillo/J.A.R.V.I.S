package com.dincr.data

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class RatingPromptTest {
    private val start = 1_800_000_000_000L
    private fun later(days: Int) = start + days * 86_400_000L

    @Test fun aNewPersonIsNotAsked() = assertFalse(RatingPrompt.shouldAsk(start, 50, null, later(6)))

    @Test fun littleUseIsNotAsked() = assertFalse(RatingPrompt.shouldAsk(start, 4, null, later(30)))

    @Test fun enoughUseIsAsked() = assertTrue(RatingPrompt.shouldAsk(start, 5, null, later(7)))

    @Test fun askedAgainOnlyAfterTheGap() {
        assertFalse(RatingPrompt.shouldAsk(start, 40, later(10), later(129)))
        assertTrue(RatingPrompt.shouldAsk(start, 40, later(10), later(130)))
    }
}
