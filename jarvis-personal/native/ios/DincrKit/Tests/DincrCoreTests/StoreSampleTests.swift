import Foundation
import Testing
@testable import DincrCore

/// The STORE sample behind the App Store screenshots (store-assets/). Same numbers as Android's
/// `StoreFixtureTest.kt`: the figures on different screens agree and nothing says "ejemplo".
@Suite struct StoreSampleTests {
    @Test func dashboardAgreesWithTheMovementsAndDebts() async throws {
        let fixture = FixtureDincrService(scenario: .store, latency: .zero, language: .spanish)
        let dashboard = try await fixture.freeDashboard()
        #expect(dashboard.month == "2026-09")
        #expect(dashboard.income == 865_000)
        #expect(dashboard.expenses == Decimal(string: "485025")!)
        #expect(dashboard.available == dashboard.income - dashboard.expenses)
        #expect(dashboard.monthlyHistory.count == 6)
        for month in dashboard.monthlyHistory {
            #expect(month.income == 865_000)
            #expect(month.expenses > 0 && month.expenses < month.income)
        }
        let debts = try await fixture.debts()
        #expect(dashboard.debtBalance == debts.reduce(Decimal(0)) { $0 + ($1.remainingAmount ?? 0) })
    }

    @Test func storeProfileIsAStorePlanWithAFirstName() async throws {
        let fixture = FixtureDincrService(scenario: .store, plan: .basic, latency: .zero, language: .spanish)
        let profile = try await fixture.me()
        #expect(profile.firstName == "Ana")
        #expect(profile.isCourtesy == false)
        let names = try await fixture.debts().compactMap(\.name) + fixture.goals().compactMap(\.name)
        #expect(!names.contains { $0.localizedCaseInsensitiveContains("ejemplo") })
    }

    @Test func englishStoreSpeaksEnglishWithTheSameNumbers() async throws {
        let english = FixtureDincrService(scenario: .store, latency: .zero, language: .english)
        let spanish = FixtureDincrService(scenario: .store, latency: .zero, language: .spanish)
        #expect(try await english.me().numberFormat == "comma_dot")
        #expect(try await english.debts().compactMap(\.name) == ["Main card", "Car loan"])
        #expect(try await english.movements().contains { $0.description == "Groceries" && $0.category == "Food" })
        #expect(try await english.freeDashboard().monthlyHistory == spanish.freeDashboard().monthlyHistory)
    }
}
