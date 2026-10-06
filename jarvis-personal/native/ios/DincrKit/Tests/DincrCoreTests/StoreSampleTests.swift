import Foundation
import Testing
@testable import DincrCore

/// The STORE sample behind the App Store screenshots (store-assets/). It is served by the same
/// `FixtureBackend` as every other fixture, and its engine screens answer exactly what the backend
/// engines computed (store-sample.json, pinned by backend/tests/test_store_sample_engine.py).
@Suite struct StoreSampleTests {
    static let native = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()

    static func service(_ language: AppLanguage, plan: PlanTier = .free) -> DincrService {
        FixtureBackend.service(FixtureBackend(scenario: .store, plan: plan, latency: .zero, language: language))
    }

    /// The bundled copy is the Android resource, byte for byte (the backend test writes both).
    @Test func bundledGoldenIsTheAndroidResource() throws {
        let android = try Data(contentsOf: Self.native.appendingPathComponent("android/core/data/src/main/resources/store-sample.json"))
        let ios = try Data(contentsOf: Self.native.appendingPathComponent("ios/DincrKit/Sources/DincrCore/Resources/store-sample.json"))
        #expect(android == ios, "store-sample.json drifted between Android and iOS: regenerate with DINCR_UPDATE_STORE_GOLDEN=1")
    }

    /// Every engine screen decodes into the app's models and matches the golden, in both languages.
    @Test func engineScreensAreTheBackendAnswers() async throws {
        for language in [AppLanguage.spanish, .english] {
            let vip = Self.service(language, plan: .vip)
            let center = try await vip.commandCenter()
            let golden = try #require(StoreSample.engine("command_center", language: language) as? [String: Any])
            let director = try #require(golden["director"] as? [String: Any])
            #expect(center.director?.priority == director["priority"] as? String)
            #expect(center.director?.headline == director["headline"] as? String)
            let roadmap = try #require(golden["roadmap"] as? [[String: Any]])
            #expect(center.roadmap?.compactMap(\.title) == roadmap.compactMap { $0["title"] as? String })
            let strategy = try await vip.strategyVip()
            #expect(strategy.priority == (StoreSample.engine("strategy_vip", language: language) as? [String: Any])?["priority"] as? String)
            let basic = Self.service(language, plan: .basic)
            let budget = try await basic.budget()
            let goldenBudget = try #require(StoreSample.engine("budget", language: language) as? [String: Any])
            #expect(budget.items?.map(\.category) == (goldenBudget["items"] as? [[String: Any]])?.compactMap { $0["category"] as? String })
            let dashboard = try await Self.service(language).freeDashboard()
            let goldenDashboard = try #require(StoreSample.engine("free_dashboard", language: language) as? [String: Any])
            #expect(dashboard.month == goldenDashboard["month"] as? String)
            #expect(dashboard.categories.map(\.category) == (goldenDashboard["categories"] as? [[String: Any]])?.compactMap { $0["category"] as? String })
        }
    }

    /// Engine screens keep the backend's plan gates: Free never gets the VIP command center.
    @Test func engineScreensKeepThePlanGates() async throws {
        let free = Self.service(.spanish)
        await #expect(throws: APIError.self) { _ = try await free.commandCenter() }
        await #expect(throws: APIError.self) { _ = try await free.budget() }
    }

    @Test func storeProfileIsAStorePlanWithAFirstName() async throws {
        let service = Self.service(.spanish, plan: .basic)
        let profile = try await service.me()
        #expect(profile.firstName == "Ana")
        #expect(profile.isCourtesy == false)
        #expect(profile.planTier == .basic)
        let names = try await service.debts().compactMap(\.name) + service.goals().compactMap(\.name)
        #expect(!names.isEmpty && !names.contains { $0.localizedCaseInsensitiveContains("ejemplo") })
    }

    @Test func englishStoreSpeaksEnglishWithTheSameNumbers() async throws {
        let english = Self.service(.english), spanish = Self.service(.spanish)
        #expect(try await english.me().numberFormat == "comma_dot")
        #expect(try await english.debts().compactMap(\.name) == ["Main card", "Car loan"])
        #expect(try await english.freeDashboard().monthlyHistory == spanish.freeDashboard().monthlyHistory)
    }

    /// A VIP store account shows a connected mailbox with the notices `pending_notices` counts.
    @Test func vipStoreHasTheMailboxAndItsNotices() async throws {
        let vip = Self.service(.spanish, plan: .vip)
        #expect(try await vip.mailStatus().isConnected)
        let pending = try await vip.mailCandidates(pendingOnly: true)
        #expect(pending.count == StoreSample.inputs(.spanish)["pending_notices"] as? Int)
        #expect(pending.contains { $0.needsRate })
    }

    /// #292: the safe-to-spend minimum is the lowest expected balance, never "commitments".
    @Test func homeLabelsTheMinimumAsTheLowestExpectedBalance() throws {
        let file = Self.native.appendingPathComponent("ios/DINCR/Features/Home/HomeBlocks.swift")
        let source = try String(contentsOf: file, encoding: .utf8)
        #expect(source.contains("Saldo mínimo previsto (45 días)") && source.contains("Lowest expected balance (45 days)"))
        #expect(!source.contains("Compromisos próximos 45 días") && !source.contains("Mínimo próximos 45 días"))
    }
}
