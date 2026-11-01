import Foundation
import Testing
@testable import DincrCore

/// Movimientos lists the month in course; the sample data must show its rows on any date, the 1st of
/// a month included (the UI tests failed on 1 November when the last days' rows fell in October).
/// Android: `FixtureMonthStartTest.kt`.
@Suite struct FixtureMonthStartTests {
    @Test func theRecentSampleRowsStayInTheMonthInCourseOnThe1st() async throws {
        let calendar = Calendar(identifier: .gregorian)
        let first = calendar.date(from: DateComponents(year: 2026, month: 11, day: 1, hour: 12))!
        let rows = try await FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero, today: first)).movements()
        for name in ["Supermercado", "Feria del agricultor", "Suscripción en dólares", "Alquiler"] {
            let row = try #require(rows.first { $0.description == name })
            #expect(row.day?.hasPrefix("2026-11") == true, "\(name) on \(row.day ?? "?")")
        }
    }
}
