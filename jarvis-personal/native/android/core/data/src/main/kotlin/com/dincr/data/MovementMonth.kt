package com.dincr.data

/**
 * Movimientos shows one month at a time (the current one when it opens), not the whole history.
 * The backend still returns every movement; this narrows what is on screen. A search looks through
 * every month, so an old movement can still be found by name. iOS: `MovementMonth.swift`.
 */
object MovementMonth {
    /** With a search, every month; without one, only [month] (`YYYY-MM`). */
    fun rows(rows: List<Movement>, month: String, query: String): List<Movement> {
        val searching = query.isNotBlank()
        return rows.filter { searching || it.day.orEmpty().startsWith(month) }
    }
}
