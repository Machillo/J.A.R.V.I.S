package com.dincr.data

import java.time.LocalDate
import java.time.temporal.ChronoUnit

/**
 * How far a scheduled day is from today, in words: "Hoy", "Mañana", "En 5 días", "Hace 2 días".
 * Only the distance: a past day doesn't say whether it was paid. A value that isn't a day has no
 * label (never a guess). iOS: `DaysLeft`.
 */
object DaysLeft {
    fun label(day: String?, today: LocalDate = LocalDate.now(), language: AppLanguage = AppLanguage.current()): String? {
        val date = day?.take(10)?.let { runCatching { LocalDate.parse(it) }.getOrNull() } ?: return null
        val days = ChronoUnit.DAYS.between(today, date)
        return when {
            days == 0L -> language.pick("Hoy", "Today")
            days == 1L -> language.pick("Mañana", "Tomorrow")
            days == -1L -> language.pick("Ayer", "Yesterday")
            days > 1 -> language.pick("En $days días", "In $days days")
            else -> language.pick("Hace ${-days} días", "${-days} days ago")
        }
    }
}
