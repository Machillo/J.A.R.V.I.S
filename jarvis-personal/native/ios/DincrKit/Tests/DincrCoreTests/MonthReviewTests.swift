import Foundation
import Testing
@testable import DincrCore

/// RV-1 — the month that closed, in three short cards. Android: `MonthReviewTest.kt`. Synthetic data.
@Suite struct MonthReviewTests {
    private let colones = MoneyFormat(currency: "CRC", separators: .dotComma)
    private func summary(_ json: String) throws -> MonthlySummary {
        try APIClient.decoder.decode(MonthlySummary.self, from: Data(json.utf8))
    }

    private let october = #"""
    {"period":"2026-10","income":1000000,"expenses":700000,"debt_paid":100000,
     "top_category":{"category":"Comida","amount":250000},"saved":{"total":50000,"goals":0,"salvavidas":50000}}
    """#
    private let september = #"{"period":"2026-09","income":1000000,"expenses":750000,"debt_paid":100000}"#

    @Test func aGoodMonthComparedWithTheOneBefore() throws {
        let cards = MonthReview.cards(try summary(october), previous: try summary(september), format: colones, language: .spanish)
        #expect(cards.map(\.title) == ["Cómo te fue en oct 2026", "Lo que lograste", "Para este mes"])
        #expect(cards[0].lines == ["Te sobraron ₡200.000.", "Es ₡50.000 mejor que el mes anterior."])
        #expect(cards[1].lines == ["Pagaste ₡100.000 de deudas.", "Guardaste ₡50.000."])
        #expect(cards[2].lines == ["Seguí igual: mantené lo que guardás y tus pagos de deudas al día."])
    }

    @Test func aMonthInTheRedPointsAtTheBiggestSpending() throws {
        let short = try summary(#"""
        {"period":"2026-10","income":500000,"expenses":600000,"debt_paid":0,"top_category":{"category":"Comida","amount":250000}}
        """#)
        let cards = MonthReview.cards(short, previous: nil, format: colones, language: .spanish)
        #expect(cards[0].lines == ["Salió ₡100.000 más de lo que entró."])
        #expect(cards[1].lines == ["Este mes no hubo pagos de deudas ni ahorro registrados."])
        #expect(cards[2].lines == ["Tu gasto más grande fue Comida (₡250.000). Bajarlo un poco es lo que más ayuda."])
    }

    @Test func nothingSavedAsksToPutSomethingAside() throws {
        let month = try summary(#"{"period":"2026-10","income":500000,"expenses":400000,"debt_paid":0}"#)
        #expect(MonthReview.cards(month, previous: nil, format: colones, language: .spanish)[2].lines
                == ["Apenas entre tu salario, apartá algo para tu Salvavidas o una meta, aunque sea poco."])
    }

    @Test func anUnknownIncomeIsNotReadAsZero() throws {
        let month = try summary(#"{"period":"2026-10","expenses":400000}"#)
        let cards = MonthReview.cards(month, previous: nil, format: colones, language: .spanish)
        #expect(MonthReview.left(month) == nil)
        #expect(cards[0].lines == ["Faltan los ingresos o los gastos de este mes para saberlo."])
    }

    @Test func theClosedMonthIsTheOneBeforeToday() {
        let calendar = Calendar(identifier: .gregorian)
        let months = MonthReview.closedMonths(today: calendar.date(from: DateComponents(year: 2027, month: 1, day: 3))!)
        #expect(months.closed == "2026-12" && months.before == "2026-11")
    }
}
