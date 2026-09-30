import Foundation
import Testing
@testable import DincrCore

/// JARVIS agenda (J2): the historical upcoming events, read defensively, grouped by day for display,
/// and fed by the same events the chat creates. Android: `JarvisAgendaTest.kt`.
@Suite struct JarvisAgendaTests {
    private func decode(_ json: String) throws -> JarvisAgendaResponse {
        try APIClient.decoder.decode(JarvisAgendaResponse.self, from: Data(json.utf8))
    }

    @Test func theAgendaReadsTheHistoricalEvents() throws {
        let response = try decode(#"""
        {"events":[{"id":7,"title":"Reunión con el contador","description":"Agendá reunión…","event_type":"personal","event_date":"2026-10-02 10:00","user_id":null,"workspace_id":"w","created_at":"2026-09-30T12:00:00"},
                   {"id":8,"title":"Cita médica","description":null,"event_type":"personal","event_date":"2026-10-09"}]}
        """#)
        #expect(response.events.map(\.title) == ["Reunión con el contador", "Cita médica"])
        let first = try #require(response.events.first)
        #expect(first.day == "2026-10-02" && first.time == "10:00" && first.eventType == "personal")
        #expect(response.events[1].time == nil)  // a day without a time shows no time, never an invented one
    }

    @Test func anUnreadableRowIsLeftOutNotTheWholeAgenda() throws {
        let response = try decode(#"""
        {"events":[{"id":1,"title":"Bien","event_date":"2026-10-02 10:00"},
                   {"title":"Sin id","event_date":"2026-10-03"},
                   {"id":3,"event_date":"2026-10-04"},
                   {"id":4,"title":null,"event_date":"2026-10-05"},
                   {"id":5,"title":"Sin fecha"},
                   "texto", 42, null]}
        """#)
        #expect(response.events.map(\.id) == [1])
    }

    @Test func anAnswerWithoutEventsIsAnError() {
        for json in [#"{}"#, #"{"events":null}"#, #"{"events":"x"}"#, #"[]"#] {
            #expect(throws: (any Error).self, "\(json)") { try decode(json) }
        }
        #expect(try decode(#"{"events":[]}"#).events.isEmpty)
    }

    @Test func eventsAreGroupedByDayInTheBackendsOrder() {
        let events = [
            JarvisEvent(id: 1, title: "A", eventDate: "2026-10-02 08:15"),
            JarvisEvent(id: 2, title: "B", eventDate: "2026-10-02 16:30"),
            JarvisEvent(id: 3, title: "C", eventDate: "2026-10-09"),
        ]
        let days = JarvisAgenda.days(events)
        #expect(days.map(\.day) == ["2026-10-02", "2026-10-09"])
        #expect(days[0].events.map(\.title) == ["A", "B"])
        #expect(events[0].date != nil)
        #expect(JarvisEvent(id: 9, title: "x", eventDate: "2026-02-30 10:00").date == nil)  // never guessed into another day
    }

    @Test func theAgendaAsksForTheHistorical45Days() async throws {
        let backend = FixtureBackend(role: .owner, latency: .zero)
        let service = FixtureBackend.service(backend)
        _ = try await service.jarvisUpcomingEvents()
        let request = try #require(await backend.requests.last)
        #expect(request.url?.path == "/jarvis/calendar/upcoming")
        #expect(request.url?.query == "days=45")
    }

    @Test func onlyTheOwnerAndAdminReachTheAgendaEndpoint() async throws {
        #expect(try await FixtureBackend.service(FixtureBackend(role: .owner, latency: .zero)).jarvisUpcomingEvents().count == 2)
        _ = try await FixtureBackend.service(FixtureBackend(role: .admin, latency: .zero)).jarvisUpcomingEvents()
        for plan in [PlanTier.free, .basic, .vip] {
            let user = FixtureBackend.service(FixtureBackend(plan: plan, latency: .zero))
            await #expect(throws: APIError.self) { try await user.jarvisUpcomingEvents() }
        }
        #expect(try await FixtureBackend.service(FixtureBackend(scenario: .empty, role: .owner, latency: .zero)).jarvisUpcomingEvents().isEmpty)
        let failing = FixtureBackend.service(FixtureBackend(scenario: .failing, role: .owner, latency: .zero))
        await #expect(throws: APIError.self) { try await failing.jarvisUpcomingEvents() }
    }

    @Test func aChatEventReachesTheAgendaOnlyOnceConfirmed() async throws {
        // Chat and agenda meet on the same data: the event is shown first, saved on "sí".
        let service = FixtureBackend.service(FixtureBackend(role: .owner, latency: .zero))
        let asked = try await service.jarvisChat("Agendá dentista el 10 de octubre a las 3pm")
        #expect(asked.awaitsConfirmation)
        #expect(try await !service.jarvisUpcomingEvents().contains { $0.title == "dentista" })
        _ = try await service.jarvisChat("sí")
        let dentist = try #require(try await service.jarvisUpcomingEvents().first { $0.title == "dentista" })
        #expect(dentist.time == "15:00")
    }
}
