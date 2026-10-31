import Foundation
import Testing
@testable import DincrCore

/// FA-1 — Análisis financiero reads the user's own twelve months in plain words: the average of the
/// complete months that recorded both income and spending, "X de cada 100", and the categories
/// already above normal this month. Unknown is never 0. Android: `FinancialAnalysisTest.kt`. Synthetic data.
@Suite struct FinancialAnalysisTests {
    private let colones = MoneyFormat(currency: "CRC", separators: .dotComma)

    private func analysis(_ json: String) throws -> FinancialAnalysis {
        try APIClient.decoder.decode(FinancialAnalysis.self, from: Data(json.utf8))
    }

    private let year = #"""
    {"months":[
      {"period":"2026-07","income":0,"expenses":0,"debt_paid":0,"saved":0,"partial":false},
      {"period":"2026-08","income":800000,"expenses":0,"debt_paid":0,"saved":0,"partial":false},
      {"period":"2026-09","income":1000000,"expenses":600000,"debt_paid":100000,"saved":50000,"partial":false},
      {"period":"2026-10","income":1000000,"expenses":700000,"debt_paid":100000,"saved":150000,"partial":false},
      {"period":"2026-11","income":1000000,"expenses":50000,"debt_paid":0,"saved":0,"partial":true}],
     "categories":[{"category":"Comida","current":90000,"average":60000},{"category":"Ropa","current":40000,"average":0},
                   {"category":"Vivienda","current":0,"average":300000},{"category":"Salud","current":20000,"average":20000}]}
    """#

    @Test func aNormalMonthAveragesOnlyCompleteMonthsWithIncomeAndSpending() throws {
        let normal = try #require(FinancialReading.normal(try analysis(year)))
        // July recorded nothing, August no spending and November is not over: only September and October.
        #expect(normal.months == 2)
        #expect(normal.income == 1_000_000 && normal.expenses == 650_000 && normal.debtPaid == 100_000 && normal.saved == 100_000)
        #expect(normal.left == 250_000)
    }

    @Test func theSentencesSayItInPlainWords() throws {
        let normal = try #require(FinancialReading.normal(try analysis(year)))
        #expect(FinancialReading.leftSentence(normal, format: colones, language: .spanish) == "En un mes normal te sobran ₡250.000.")
        #expect(FinancialReading.leftExplanation(normal, format: colones, language: .spanish)
                == "Entra ₡1.000.000, gastás ₡650.000 y pagás ₡100.000 de deudas. Es el promedio de tus últimos 2 meses completos.")
        #expect(FinancialReading.savedSentence(normal, language: .spanish) == "Guardás 10 de cada 100 que entran.")
        #expect(FinancialReading.debtSentence(normal, language: .spanish) == "De cada 100 que entran, 10 se van a pagar deudas.")
    }

    @Test func spendingMoreThanWhatComesInIsSaidAsSuch() {
        let short = FinancialAnalysis(months: [.init(period: "2026-09", income: 500_000, expenses: 600_000, debtPaid: 50_000)])
        let normal = FinancialReading.normal(short)!
        #expect(FinancialReading.leftSentence(normal, format: colones, language: .spanish) == "En un mes normal sale ₡150.000 más de lo que entra.")
        #expect(FinancialReading.leftExplanation(normal, format: colones, language: .spanish).hasSuffix("Es el promedio de tu último mes completo."))
        #expect(FinancialReading.savedSentence(normal, language: .spanish) == "Todavía no estás guardando parte de lo que entra.")
    }

    @Test func withoutAComparableMonthThereIsNoNormalMonth() {
        let onlyIncome = FinancialAnalysis(months: [.init(period: "2026-10", income: 900_000, expenses: 0),
                                                    .init(period: "2026-11", income: 900_000, expenses: 300_000, partial: true)])
        #expect(FinancialReading.normal(onlyIncome) == nil, "the month in course is never a normal month")
        #expect(FinancialReading.debtSentence(FinancialReading.Normal(months: 1, income: 0, expenses: 1, debtPaid: 1, saved: 0)) == nil, "no income: no share")
    }

    @Test func noDebtPaymentsNoDebtSentence() {
        let normal = FinancialReading.Normal(months: 1, income: 100, expenses: 50, debtPaid: 0, saved: 0)
        #expect(FinancialReading.debtSentence(normal) == nil)
    }

    @Test func onlyCategoriesAlreadyAboveNormalAreListedLargestFirst() throws {
        let rises = FinancialReading.rises(try analysis(year))
        #expect(rises.map(\.category) == ["Ropa", "Comida"], "Vivienda is below (the month is not over) and Salud is the same")
        #expect(FinancialReading.riseLine(rises[1], format: colones, language: .spanish) == "Comida: ₡90.000 este mes · normalmente ₡60.000")
        #expect(FinancialReading.canCompare(try analysis(year)))
    }

    @Test func withoutEarlierMonthsNothingIsCompared() throws {
        let first = try analysis(#"{"months":[],"categories":[{"category":"Comida","current":90000,"average":null}]}"#)
        #expect(FinancialReading.rises(first).isEmpty)
        #expect(!FinancialReading.canCompare(first))
    }

    @Test func theBarsSkipMonthsWithNothingRecorded() throws {
        #expect(FinancialReading.chartMonths(try analysis(year)).map(\.month) == ["2026-08", "2026-09", "2026-10", "2026-11"])
    }

    @Test func theFixtureGivesVipAndTheOwnerAComparableYearAndRefusesTheRest() async throws {
        for role in [FixtureBackend.Role.user, .owner] {
            let analysis = try await FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, role: role, latency: .zero)).financialAnalysis()
            #expect(analysis.months.count == 12)
            #expect(analysis.months.filter { $0.partial == true }.count == 1)
            #expect(FinancialReading.savedSentence(try #require(FinancialReading.normal(analysis)), language: .spanish) == "Guardás 10 de cada 100 que entran.")
            #expect(FinancialReading.rises(analysis).map(\.category) == ["Comida"])
        }
        for plan in [PlanTier.free, .basic] {
            await #expect(throws: (any Error).self) {
                try await FixtureBackend.service(FixtureBackend(scenario: .populated, plan: plan, latency: .zero)).financialAnalysis()
            }
        }
    }
}
