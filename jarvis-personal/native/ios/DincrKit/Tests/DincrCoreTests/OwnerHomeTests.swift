import Foundation
import Testing
@testable import DincrCore

/// The Owner's "Hoy" and JARVIS chat entry points (presentation rules only; synthetic data).
@Suite struct OwnerHomeTests {
    private func center(_ json: String) throws -> CommandCenter {
        try APIClient.decoder.decode(CommandCenter.self, from: Data(json.utf8))
    }

    private func at(hour: Int) -> Date {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/Costa_Rica")!
        return calendar.date(from: DateComponents(year: 2026, month: 10, day: 1, hour: hour, minute: 30))!
    }

    @Test func theGreetingFollowsThePartOfTheDay() {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/Costa_Rica")!
        #expect(OwnerHome.greeting(at: at(hour: 4), calendar: calendar) == .evening)
        #expect(OwnerHome.greeting(at: at(hour: 5), calendar: calendar) == .morning)
        #expect(OwnerHome.greeting(at: at(hour: 11), calendar: calendar) == .morning)
        #expect(OwnerHome.greeting(at: at(hour: 12), calendar: calendar) == .afternoon)
        #expect(OwnerHome.greeting(at: at(hour: 18), calendar: calendar) == .afternoon)
        #expect(OwnerHome.greeting(at: at(hour: 19), calendar: calendar) == .evening)
    }

    @Test func attentionPutsMailFirstThenUrgentAlertsAndKeepsTheBackendsWords() throws {
        let value = try center(#"""
        {"alerts":[{"severity":"medium","title":"Pago en 5 días","context":"El mínimo vence pronto.","action":"Revisá la deuda"},
                   {"severity":"high","title":"Saldo bajo","context":null,"action":null},
                   {"severity":"high","title":"  ","context":"sin título"}],
         "automation":{"confirmed":4,"review":3,"duplicates":0}}
        """#)
        let items = OwnerHome.attention(from: value)
        #expect(items.map(\.kind) == [.mailReview, .urgentAlert, .alert])
        #expect(items[0].count == 3)
        #expect(items[1].title == "Saldo bajo" && items[1].detail == nil)
        #expect(items[2].title == "Pago en 5 días" && items[2].detail == "El mínimo vence pronto. Revisá la deuda")
    }

    @Test func nothingPendingMeansNoAttentionItems() throws {
        #expect(OwnerHome.attention(from: nil).isEmpty)
        #expect(OwnerHome.attention(from: try center(#"{"automation":{"review":0},"alerts":[]}"#)).isEmpty)
        #expect(OwnerHome.attention(from: try center(#"{}"#)).isEmpty)
    }

    @Test func upcomingKeepsTheAgendaOrderAndLimit() {
        let events = (1...5).map { JarvisEvent(id: $0, title: "E\($0)", eventDate: "2026-10-0\($0)") }
        #expect(OwnerHome.upcoming(events).map(\.id) == [1, 2, 3])
        #expect(OwnerHome.upcoming(events, limit: 1).map(\.id) == [1])
        #expect(OwnerHome.upcoming([], limit: 3).isEmpty)
        #expect(OwnerHome.upcoming(events, limit: -1).isEmpty)
    }

    @Test func theChatOffersOnlyItsDeliberateScope() {
        // OT, bonuses and the agenda; never a general financial assistant.
        #expect(JarvisQuickAction.allCases == [.overtime, .bonus, .schedule, .agenda])
        let phrases = JarvisQuickAction.allCases.compactMap(\.composerText)
        #expect(phrases == ["Hoy hice ", "Recibí un bono de ", "Agendá "])
        for forbidden in ["gast", "deuda", "invert", "correo", "presupuesto", "finanzas"] {
            #expect(!phrases.contains { $0.lowercased().contains(forbidden) }, "\(forbidden)")
        }
        // Only "Ver mi agenda" navigates; it never writes anything to the composer.
        #expect(JarvisQuickAction.allCases.filter(\.opensAgenda) == [.agenda])
        #expect(JarvisQuickAction.agenda.composerText == nil)
    }

    @Test func theOwnerHomeDataComesFromTheOwnersOwnRoutes() async throws {
        // The fixture server answers the command center and the agenda for the Owner; a VIP user gets
        // the command center but never the agenda (the backend decides).
        let owner = FixtureBackend.service(FixtureBackend(role: .owner, latency: .zero))
        let center = try await owner.commandCenter()
        #expect(center.safeToSpend?.amount != nil)
        #expect(OwnerHome.upcoming(try await owner.jarvisUpcomingEvents()).count == 2)
        let vip = FixtureBackend.service(FixtureBackend(plan: .vip, latency: .zero))
        _ = try await vip.commandCenter()
        await #expect(throws: APIError.self) { try await vip.jarvisUpcomingEvents() }
    }
}
