package com.dincr.data

/**
 * When to offer the store's own rating dialog. A person is asked only after real use and never
 * often; the store still decides whether the dialog shows, and DINCR never learns the answer.
 * iOS twin: `RatingPrompt.swift`.
 */
object RatingPrompt {
    const val MINIMUM_DAYS = 7
    const val MINIMUM_SAVES = 5
    const val DAYS_BETWEEN_ASKS = 120
    private const val DAY_MS = 86_400_000L

    fun shouldAsk(firstOpenMs: Long, saves: Int, lastAskedMs: Long?, nowMs: Long): Boolean {
        if (saves < MINIMUM_SAVES || (nowMs - firstOpenMs) / DAY_MS < MINIMUM_DAYS) return false
        lastAskedMs ?: return true
        return (nowMs - lastAskedMs) / DAY_MS >= DAYS_BETWEEN_ASKS
    }
}
