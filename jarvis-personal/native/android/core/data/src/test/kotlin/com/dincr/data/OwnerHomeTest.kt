package com.dincr.data

import org.junit.Assert.assertEquals
import org.junit.Test

/** The Owner's JARVIS space on Hoy: the same greeting and agenda rules as iOS (`OwnerHomeTests`). */
class OwnerHomeTest {
    @Test fun theGreetingFollowsThePartOfTheDay() {
        assertEquals(OwnerHome.Greeting.MORNING, OwnerHome.greeting(5))
        assertEquals(OwnerHome.Greeting.MORNING, OwnerHome.greeting(11))
        assertEquals(OwnerHome.Greeting.AFTERNOON, OwnerHome.greeting(12))
        assertEquals(OwnerHome.Greeting.AFTERNOON, OwnerHome.greeting(18))
        assertEquals(OwnerHome.Greeting.EVENING, OwnerHome.greeting(19))
        assertEquals(OwnerHome.Greeting.EVENING, OwnerHome.greeting(4))
    }

    @Test fun theNextEventsKeepTheBackendsOrder() {
        val events = (1L..5L).map { JarvisEvent(it, "Evento $it", "2026-10-1$it") }
        assertEquals(listOf(1L, 2L, 3L), OwnerHome.upcoming(events).map { it.id })
        assertEquals(emptyList<JarvisEvent>(), OwnerHome.upcoming(events, limit = 0))
    }
}
