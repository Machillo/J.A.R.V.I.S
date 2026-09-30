package com.dincr.data

import java.time.LocalDate
import java.time.format.DateTimeParseException
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.longOrNull

/**
 * The Owner's agenda (JARVIS recovery, J2): the historical "Próximos eventos" of JARVIS.
 *
 * `GET /jarvis/calendar/upcoming?days=45` answers `{"events": [...]}`: rows of the historical `events`
 * table, from today to 45 days out, in chronological order. The same events the chat answers
 * "¿qué tengo?" with, and the ones a confirmed chat event adds; events are created only through the
 * chat, as they always were. iOS twin: `JarvisAgenda.swift`.
 */
object JarvisAgenda {
    /** The horizon of the historical agenda card (backend `AGENDA_DAYS`). */
    const val DAYS = 45

    /** One day of the agenda: its events, in the backend's order. */
    data class Day(val day: String, val events: List<JarvisEvent>)

    /** Groups the events by day (presentation only), keeping the backend's chronological order. */
    fun days(events: List<JarvisEvent>): List<Day> =
        events.groupBy { it.day }.map { (day, items) -> Day(day, items) }

    /** The events of `{"events": [...]}`; a row that cannot be read is left out, a body without the list is null. */
    fun from(element: JsonElement): List<JarvisEvent>? {
        val rows = (element as? JsonObject)?.get("events") as? JsonArray ?: return null
        return rows.mapNotNull { JarvisEvent.from(it) }
    }
}

/**
 * One row of the `events` table as the backend sends it. Only `id`, `title` and `event_date` are
 * required; `event_date` is the stored text ("YYYY-MM-DD" or "YYYY-MM-DD HH:MM") and is shown, not
 * reinterpreted.
 */
data class JarvisEvent(val id: Long, val title: String, val eventDate: String, val eventType: String? = null, val description: String? = null) {
    /** "YYYY-MM-DD": the day the backend filtered and sorted by. */
    val day: String get() = eventDate.trim().take(10)

    /** "HH:MM" when the stored date carries a time, null otherwise. */
    val time: String? get() = eventDate.trim().drop(10).trim(' ', 'T').take(5).ifEmpty { null }

    /** The day as a date (presentation), null if the text is not a real day. */
    val date: LocalDate? get() = try { LocalDate.parse(day) } catch (_: DateTimeParseException) { null }

    companion object {
        fun from(element: JsonElement): JarvisEvent? {
            val row = element as? JsonObject ?: return null
            fun text(key: String) = (row[key] as? JsonPrimitive)?.takeIf { it.isString }?.content
            val id = (row["id"] as? JsonPrimitive)?.takeIf { !it.isString }?.longOrNull ?: return null
            val title = text("title") ?: return null
            val eventDate = text("event_date") ?: return null
            return JarvisEvent(id, title, eventDate, text("event_type"), text("description"))
        }
    }
}
