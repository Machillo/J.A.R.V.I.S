package com.dincr.data

import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * JARVIS agenda (J2): the historical upcoming events, read defensively, grouped by day for display, and
 * fed by the same events the chat creates. The Swift twin is `JarvisAgendaTests`.
 */
class JarvisAgendaTest {
    private val json = Json { ignoreUnknownKeys = true }
    private fun read(body: String) = JarvisAgenda.from(json.parseToJsonElement(body))

    private fun fixture(role: FakeBackend.Role = FakeBackend.Role.OWNER, plan: PlanTier = PlanTier.FREE, scenario: FakeBackend.Scenario = FakeBackend.Scenario.POPULATED) =
        FakeBackend(scenario, plan, role = role).let { backend -> backend to DincrApi(ApiClient("https://fixtures.invalid", { "t" }, backend, AppLanguage.SPANISH, backoff = {})) }

    @Test fun theAgendaReadsTheHistoricalEvents() {
        val events = read("""{"events":[{"id":7,"title":"Reunión con el contador","description":"Agendá reunión…","event_type":"personal","event_date":"2026-10-02 10:00","user_id":null,"workspace_id":"w","created_at":"2026-09-30T12:00:00"},
            {"id":8,"title":"Cita médica","description":null,"event_type":"personal","event_date":"2026-10-09"}]}""")!!
        assertEquals(listOf("Reunión con el contador", "Cita médica"), events.map { it.title })
        assertEquals("2026-10-02", events[0].day)
        assertEquals("10:00", events[0].time)
        assertEquals("personal", events[0].eventType)
        assertNull(events[1].time)  // a day without a time shows no time, never an invented one
    }

    @Test fun anUnreadableRowIsLeftOutNotTheWholeAgenda() {
        val events = read("""{"events":[{"id":1,"title":"Bien","event_date":"2026-10-02 10:00"},{"title":"Sin id","event_date":"2026-10-03"},
            {"id":3,"event_date":"2026-10-04"},{"id":4,"title":null,"event_date":"2026-10-05"},{"id":5,"title":"Sin fecha"},{"id":"6","title":"Id texto","event_date":"2026-10-06"},"texto",42,null]}""")!!
        assertEquals(listOf(1L), events.map { it.id })
    }

    @Test fun anAnswerWithoutEventsIsNotAnAgenda() {
        listOf("{}", """{"events":null}""", """{"events":"x"}""", "[]").forEach { assertNull(it, read(it)) }
        assertEquals(emptyList<JarvisEvent>(), read("""{"events":[]}"""))
    }

    @Test fun eventsAreGroupedByDayInTheBackendsOrder() {
        val events = listOf(JarvisEvent(1, "A", "2026-10-02 08:15"), JarvisEvent(2, "B", "2026-10-02 16:30"), JarvisEvent(3, "C", "2026-10-09"))
        val days = JarvisAgenda.days(events)
        assertEquals(listOf("2026-10-02", "2026-10-09"), days.map { it.day })
        assertEquals(listOf("A", "B"), days[0].events.map { it.title })
        assertTrue(events[0].date != null)
        assertNull(JarvisEvent(9, "x", "2026-02-30 10:00").date)  // never guessed into another day
    }

    @Test fun theAgendaAsksForTheHistorical45Days() = runTest {
        val (backend, api) = fixture()
        api.jarvisUpcomingEvents()
        val url = backend.requests.last().url
        assertTrue(url, url.endsWith("/jarvis/calendar/upcoming?days=45"))
    }

    @Test fun onlyTheOwnerAndAdminReachTheAgendaEndpoint() = runTest {
        assertEquals(2, fixture().second.jarvisUpcomingEvents().size)
        fixture(FakeBackend.Role.ADMIN).second.jarvisUpcomingEvents()
        PlanTier.entries.forEach { plan ->
            val error = runCatching { fixture(FakeBackend.Role.USER, plan).second.jarvisUpcomingEvents() }.exceptionOrNull() as ApiError
            assertEquals(ApiError.Kind.FORBIDDEN, error.kind)
        }
        assertTrue(fixture(scenario = FakeBackend.Scenario.EMPTY).second.jarvisUpcomingEvents().isEmpty())
        assertTrue(runCatching { fixture(scenario = FakeBackend.Scenario.FAILING).second.jarvisUpcomingEvents() }.exceptionOrNull() is ApiError)
    }

    @Test fun aChatEventReachesTheAgendaOnlyOnceConfirmed() = runTest {
        // Chat and agenda meet on the same data: the event is shown first, saved on "sí".
        val api = fixture().second
        assertTrue(api.jarvisChat("Agendá dentista el 10 de octubre a las 3pm").awaitsConfirmation)
        assertFalse(api.jarvisUpcomingEvents().any { it.title == "dentista" })
        api.jarvisChat("sí")
        assertEquals("15:00", api.jarvisUpcomingEvents().single { it.title == "dentista" }.time)
    }
}
