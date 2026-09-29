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

    /// The backend's own output for this account (store-sample.json, pinned by
    /// backend/tests/test_store_sample_engine.py): the iOS dashboard and debts must match it.
    @Test func dashboardAndDebtsMatchTheBackendEngines() async throws {
        let native = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let data = try Data(contentsOf: native.appendingPathComponent("android/core/data/src/main/resources/store-sample.json"))
        let golden = try #require(try JSONSerialization.jsonObject(with: data) as? [String: Any])
        func number(_ value: Any?) -> Double { (value as? NSNumber)?.doubleValue ?? .nan }
        func near(_ a: Decimal?, _ b: Any?) -> Bool { abs(NSDecimalNumber(decimal: a ?? .nan).doubleValue - number(b)) < 0.005 }
        for (code, language) in [("es", AppLanguage.spanish), ("en", AppLanguage.english)] {
            let entry = try #require(golden[code] as? [String: Any])
            let engine = try #require(entry["engine"] as? [String: Any])
            let backend = try #require(engine["free_dashboard"] as? [String: Any])
            let fixture = FixtureDincrService(scenario: .store, latency: .zero, language: language)
            let dashboard = try await fixture.freeDashboard()
            #expect(dashboard.month == backend["month"] as? String)
            #expect(near(dashboard.income, backend["income"]) && near(dashboard.expenses, backend["expenses"]))
            #expect(near(dashboard.available, backend["available_after_commitments"]) && near(dashboard.debtBalance, backend["debt_balance"]))
            let categories = try #require(backend["categories"] as? [[String: Any]])
            #expect(dashboard.categories.map(\.category) == categories.compactMap { $0["category"] as? String })
            for (mine, theirs) in zip(dashboard.categories, categories) { #expect(near(mine.amount, theirs["amount"])) }
            let history = try #require(backend["monthly_history"] as? [[String: Any]])
            #expect(dashboard.monthlyHistory.map(\.month) == history.compactMap { $0["month"] as? String })
            for (mine, theirs) in zip(dashboard.monthlyHistory, history) {
                #expect(near(mine.income, theirs["income"]) && near(mine.expenses, theirs["expenses"]))
            }
            let inputs = try #require(entry["inputs"] as? [String: Any])
            let debts = try #require(inputs["debts"] as? [[String: Any]])
            let mine = try await fixture.debts()
            #expect(mine.compactMap(\.name) == debts.compactMap { $0["name"] as? String })
            for (a, b) in zip(mine, debts) { #expect(near(a.remainingAmount, b["remaining_amount"]) && near(a.monthlyPayment, b["monthly_payment"])) }
        }
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
