import Foundation
import Testing
@testable import DincrCore

@Suite struct DaysLeftTests {
    private func label(_ day: String?) -> String? { DaysLeft.label(day, today: "2026-11-03", language: .spanish) }

    @Test func saysTheDistanceInWords() {
        #expect(label("2026-11-03") == "Hoy")
        #expect(label("2026-11-04") == "Mañana")
        #expect(label("2026-11-05") == "En 2 días")
        #expect(label("2026-12-03") == "En 30 días")
        #expect(label("2026-11-02") == "Ayer")
        #expect(label("2026-11-01") == "Hace 2 días")
    }

    @Test func readsADayWithATime() {
        #expect(label("2026-11-08T10:00:00") == "En 5 días")
    }

    @Test func aChangeOfYearCounts() {
        #expect(DaysLeft.label("2027-01-02", today: "2026-12-31", language: .spanish) == "En 2 días")
    }

    @Test func notADayHasNoLabel() {
        #expect(label(nil) == nil)
        #expect(label("") == nil)
        #expect(label("pronto") == nil)
    }
}
