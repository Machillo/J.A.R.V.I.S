import Foundation
import Testing
@testable import DincrCore

/// E04 / E05 — Análisis → Resumen del mes draws the month's own summary: income vs expenses as bars
/// with the exact amounts, expenses by category as a donut with shares computed from those amounts.
/// Unknown is never 0, nothing is made up. Android: `SummaryVisualsTest.kt`. Synthetic data.
@Suite struct SummaryVisualsTests {
    private func summary(_ json: String) throws -> MonthlySummary {
        try APIClient.decoder.decode(MonthlySummary.self, from: Data(json.utf8))
    }

    private let month = #"""
    {"period":"2026-10","income":850000,"expenses":400000,"debt_paid":0,"balance":450000,
     "categories":[{"category":"Comida","amount":200000},{"category":"Vivienda","amount":150000},{"category":"Transporte","amount":50000}]}
    """#

    @Test func theBarsAreTheMonthsIncomeAndExpensesExactly() throws {
        #expect(SummaryVisuals.flow(try summary(month)) == .bars(MonthTotals(month: "2026-10", income: 850000, expenses: 400000)))
        #expect(SummaryVisuals.flowNotice(SummaryVisuals.flow(try summary(month))) == nil)
    }

    @Test func anUnknownIncomeOrExpenseDrawsNoBars() throws {
        for json in [#"{"period":"2026-10","expenses":400000}"#, #"{"period":"2026-10","income":850000}"#, #"{"period":"2026-10","income":null,"expenses":null}"#] {
            #expect(SummaryVisuals.flow(try summary(json)) == .incomplete, "\(json)")
        }
        #expect(SummaryVisuals.flowNotice(.incomplete, language: .spanish) == "Faltan los ingresos o los gastos de este mes, así que no los comparamos.")
    }

    @Test func aMonthWithNothingRecordedIsEmptyButOneSideAtZeroIsStillCompared() throws {
        #expect(SummaryVisuals.flow(try summary(#"{"period":"2026-10","income":0,"expenses":0}"#)) == .empty)
        #expect(SummaryVisuals.flowNotice(.empty, language: .spanish) == "Todavía no hay ingresos ni gastos registrados en este mes.")
        #expect(SummaryVisuals.flow(try summary(#"{"period":"2026-10","income":0,"expenses":120000}"#))
                == .bars(MonthTotals(month: "2026-10", income: 0, expenses: 120000)))
    }

    @Test func theCategoriesAndTheirSharesComeFromTheAmounts() throws {
        let donut = SummaryVisuals.categories(try summary(month), language: .spanish)
        #expect(donut.status == .complete)
        #expect(donut.segments.map(\.label) == ["Comida", "Vivienda", "Transporte"], "the backend's order, largest first")
        #expect(donut.segments.map(\.value) == [200000, 150000, 50000])
        #expect(donut.segments.map(\.share) == [0.5, 0.375, 0.125])
        #expect(donut.spokenParts(format: MoneyFormat(), language: .spanish).count == 3)
    }

    @Test func aCategoryWithoutAnAmountKeepsTheDonutUndrawnAndIsNotZero() throws {
        let json = #"{"period":"2026-10","income":850000,"expenses":400000,"categories":[{"category":"Comida","amount":200000},{"category":"Salud","amount":null}]}"#
        let donut = SummaryVisuals.categories(try summary(json), language: .spanish)
        #expect(donut.status == .partial)
        #expect(!donut.isDrawable)
        #expect(donut.segments.map(\.share) == [nil])
        #expect(donut.unknown.map(\.label) == ["Salud"])
        #expect(donut.total == nil)
    }

    @Test func aCategoryWithoutANameIsSaidSoNotInvented() throws {
        let json = #"{"period":"2026-10","categories":[{"category":null,"amount":1000},{"category":"","amount":500}]}"#
        let donut = SummaryVisuals.categories(try summary(json), language: .spanish)
        #expect(donut.segments.map(\.label) == ["Sin categoría", "Sin categoría"])
        #expect(Set(donut.segments.map(\.id)).count == 2, "two rows stay two parts")
    }

    @Test func noCategoriesIsAnEmptyDonut() throws {
        #expect(SummaryVisuals.categories(try summary(#"{"period":"2026-10","income":0,"expenses":0,"categories":[]}"#)).status == .empty)
        #expect(SummaryVisuals.categories(try summary(#"{"period":"2026-10"}"#)).status == .empty)
    }

    @Test func theFixtureMonthDrawsBothChartsFromItsOwnMovements() async throws {
        let service = FixtureBackend.service(FixtureBackend(scenario: .populated, latency: .zero))
        let today = String(FixtureBackend.day(0, today: .now).prefix(7))
        let current = try await service.monthlySummary(period: today)
        guard case .bars(let bars) = SummaryVisuals.flow(current) else { Issue.record("no bars"); return }
        #expect(bars.income == current.income && bars.expenses == current.expenses)
        let donut = SummaryVisuals.categories(current)
        #expect(donut.status == .complete)
        #expect(donut.segments.reduce(Decimal(0)) { $0 + $1.value } == current.expenses, "the parts are the month's expenses")

        let empty = try await FixtureBackend.service(FixtureBackend(scenario: .empty, latency: .zero)).monthlySummary(period: today)
        #expect(SummaryVisuals.flow(empty) == .empty)
        #expect(SummaryVisuals.categories(empty).status == .empty)
    }
}
