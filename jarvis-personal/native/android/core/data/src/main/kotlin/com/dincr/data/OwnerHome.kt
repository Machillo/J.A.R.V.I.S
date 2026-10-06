package com.dincr.data

/**
 * The Owner's "Hoy" (presentation only): the greeting and the next agenda events of its JARVIS
 * space, which comes first; the financial blocks are `HomeToday`. iOS twin: `OwnerHome.swift`.
 */
object OwnerHome {
    /** The part of the day the greeting names (device clock). */
    enum class Greeting { MORNING, AFTERNOON, EVENING }

    /** 05:00–11:59 morning, 12:00–18:59 afternoon, otherwise evening. */
    fun greeting(hour: Int): Greeting = when (hour) {
        in 5..11 -> Greeting.MORNING
        in 12..18 -> Greeting.AFTERNOON
        else -> Greeting.EVENING
    }

    /** The next events of the agenda, in the backend's chronological order. */
    fun upcoming(events: List<JarvisEvent>, limit: Int = 3): List<JarvisEvent> = events.take(maxOf(0, limit))
}
