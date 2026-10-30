import Foundation
import Testing
@testable import DincrCore

/// Movimientos shows one month; a search looks through every month. Synthetic rows only.
/// Android: `MovementMonthTest.kt`.
@Suite struct MovementMonthTests {
    static func row(_ id: String, _ day: String, _ description: String) -> Movement {
        Movement(movementId: id, sourceId: 1, origin: "expense", transactionDate: day, description: description, amount: 1_000,
                 transactionType: .expense, category: "Comida", notes: nil, editable: true)
    }

    let rows = [row("a", "2026-10-30", "Café de ejemplo"), row("b", "2026-10-01", "Super de ejemplo"), row("c", "2026-09-30", "Café de septiembre")]

    @Test func onlyTheMonthIsListed() {
        #expect(MovementMonth.rows(rows, month: "2026-10", query: "").map(\.movementId) == ["a", "b"])
        #expect(MovementMonth.rows(rows, month: "2026-09", query: " ").map(\.movementId) == ["c"])
        #expect(MovementMonth.rows(rows, month: "2026-08", query: "").isEmpty)
    }

    @Test func aSearchLooksThroughEveryMonth() {
        #expect(MovementMonth.rows(rows, month: "2026-10", query: "café").count == 3)
    }
}
