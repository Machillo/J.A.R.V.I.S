import Foundation
import Testing
@testable import DincrCore

/// HS-1 — the simple health reading: one word, the main reason, one action. Android: `HealthReadingTest.kt`.
@Suite struct HealthReadingTests {
    private func normal(income: Decimal = 1_000_000, expenses: Decimal = 600_000, debt: Decimal = 100_000, saved: Decimal = 150_000) -> FinancialReading.Normal {
        FinancialReading.Normal(months: 3, income: income, expenses: expenses, debtPaid: debt, saved: saved)
    }

    @Test func spendingMoreThanWhatComesInIsAtRisk() {
        let reading = HealthReading.reading(normal(expenses: 1_000_000), coverageMonths: 5, language: .spanish)
        #expect(reading?.level == .atRisk && reading?.word == "En riesgo")
        #expect(reading?.reason == "En un mes normal sale más plata de la que entra.")
    }

    @Test func heavyDebtIsAtRiskAndPointsToTheScenarios() {
        let reading = HealthReading.reading(normal(expenses: 300_000, debt: 450_000), coverageMonths: 5, language: .spanish)
        #expect(reading?.level == .atRisk && reading?.reason == "Las deudas se llevan 45 de cada 100 que entran.")
        #expect(reading?.action.contains("Escenarios") == true)
    }

    @Test func aThinSalvavidasIsAtRiskButAnUnknownOneIsLeftOut() {
        #expect(HealthReading.reading(normal(), coverageMonths: 0.3, language: .spanish)?.level == .atRisk)
        #expect(HealthReading.reading(normal(), coverageMonths: nil, language: .spanish)?.level == .good)
    }

    @Test func littleSavingOrSomeDebtIsFair() {
        #expect(HealthReading.reading(normal(saved: 50_000), coverageMonths: 5, language: .spanish)?.reason == "Guardás 5 de cada 100 que entran.")
        #expect(HealthReading.reading(normal(debt: 250_000), coverageMonths: 5, language: .spanish)?.level == .fair)
        #expect(HealthReading.reading(normal(), coverageMonths: 1.5, language: .spanish)?.reason == "Tu Salvavidas cubre 1,5 meses; lo ideal son tres.")
    }

    @Test func everythingInPlaceIsGoodAndNoNormalMonthIsNoReading() {
        #expect(HealthReading.reading(normal(), coverageMonths: 4, language: .spanish)?.word == "Bien")
        #expect(HealthReading.reading(nil, coverageMonths: 4) == nil)
    }
}
