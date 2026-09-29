import Foundation
import Testing
@testable import DincrCore

/// The RC layer shared with Android (`NativeRcTest.kt`): plan gates, kill switches, gates'
/// contracts and money-safety guards on debt payments and goal contributions.
@Suite struct NativeRcTests {
    func client(_ transport: ScriptedTransport) -> APIClient {
        APIClient(baseURL: URL(string: "https://api.example.test")!, tokens: CountingTokens(), transport: transport, language: .spanish, backoff: { _ in })
    }

    // MARK: Plans

    @Test func planMinimumsMatchTheBackendTable() {
        #expect(PlanTier.free.allows(.debts) && PlanTier.free.allows(.goals) && PlanTier.free.allows(.transactions))
        #expect(!PlanTier.free.allows(.guidedBudget) && !PlanTier.free.allows(.strategyVip))
        #expect(PlanTier.basic.allows(.guidedBudget) && !PlanTier.basic.allows(.gmailAutomation))
        #expect(Feature.allCases.allSatisfy { PlanTier.vip.allows($0) })
    }

    @Test func unknownPlanCodesAreFree() {
        #expect(PlanTier.from(nil) == .free)
        #expect(PlanTier.from("owner") == .free)
        #expect(PlanTier.from("VIP") == .vip)
    }

    @Test func unknownFlagsUseTheBackendSafeDefault() {
        #expect(!FeatureFlags.unknown.isEnabled(.financialWrites))
        #expect(!FeatureFlags.unknown.isEnabled(.gmailAutomation))
        #expect(!FeatureFlags.unknown.isEnabled(.storeBilling))
        #expect(FeatureFlags.unknown.isEnabled(.vipIntelligence))
        let loaded = FeatureFlags(flags: [.init(flagKey: "financial_writes", enabled: false, disabledMessageEs: "Pausa", disabledMessageEn: "Paused")])
        #expect(!loaded.isEnabled(.financialWrites))
        #expect(loaded.message(.financialWrites, language: .english) == "Paused")
    }

    @Test func paidPlansNeedTheLaunchPromotion() {
        let free = PlanOption(code: "free", name: "Free")
        let vip = PlanOption(code: "vip", name: "VIP")
        #expect(!PlanOffer.promotionActive(options: [free, vip], catalog: nil))
        #expect(PlanOffer.canChoose(free, promotionActive: false))
        #expect(!PlanOffer.canChoose(vip, promotionActive: false))
        let promoted = BillingCatalog(plans: nil, promotion: Promotion(active: true), notice: nil)
        #expect(PlanOffer.promotionActive(options: [free, vip], catalog: promoted))
    }

    @Test func appLockAfterFiveMinutesInBackground() {
        #expect(!AppLockPolicy.shouldLock(enabled: false, backgroundedAt: 0, now: 10_000))
        #expect(!AppLockPolicy.shouldLock(enabled: true, backgroundedAt: nil, now: 10_000))
        #expect(!AppLockPolicy.shouldLock(enabled: true, backgroundedAt: 0, now: 299))
        #expect(AppLockPolicy.shouldLock(enabled: true, backgroundedAt: 0, now: 300))
    }

    // MARK: Kill switch

    @Test func killSwitchIsAFeatureUnavailableErrorAndIsNotRetried() async throws {
        let body = #"{"detail":"Pagos en mantenimiento","code":"feature_temporarily_unavailable","feature":"financial_writes"}"#
        let transport = ScriptedTransport([.status(503, body), .status(200, "[]")])
        await #expect(throws: APIError.self) {
            let _: [Debt] = try await client(transport).get("/user-product/finance/debts")
        }
        #expect(transport.requests.count == 1)
        do {
            let _: [Debt] = try await client(ScriptedTransport([.status(503, body)])).get("/x")
        } catch let error as APIError {
            #expect(error.kind == .featureUnavailable)
            #expect(error.feature == "financial_writes")
            #expect(error.message == "Pagos en mantenimiento")
            #expect(!error.isTransient)
        }
    }

    @Test func aPlain503IsStillRetried() async throws {
        let transport = ScriptedTransport([.status(503, "{}"), .status(200, "[]")])
        let _: [Debt] = try await client(transport).get("/user-product/finance/debts")
        #expect(transport.requests.count == 2)
    }

    // MARK: Contracts

    @Test func legalAcceptSendsTheVersionsItWasAskedFor() async throws {
        let transport = ScriptedTransport([.status(200, #"{"status":"ok","required":false}"#)])
        let service = LiveDincrService(client: client(transport))
        _ = try await service.acceptLegal(LegalAcceptRequest(termsVersion: "2026-09", privacyVersion: "2026-08"))
        let request = try #require(transport.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.path == "/auth/legal/accept")
        let body = try #require(JSONSerialization.jsonObject(with: request.httpBody ?? Data()) as? [String: Any])
        #expect(body["accept_terms"] as? Bool == true)
        #expect(body["accept_privacy"] as? Bool == true)
        #expect(body["terms_version"] as? String == "2026-09")
        #expect(body["privacy_version"] as? String == "2026-08")
    }

    @Test func planChoiceSendsTheBackendConsentVersion() async throws {
        let transport = ScriptedTransport([.status(200, #"{"status":"ok","plan":"free"}"#)])
        let result = try await LiveDincrService(client: client(transport)).choosePlan(PlanChangeRequest(plan: "free"))
        #expect(result.plan == "free")
        let body = try #require(JSONSerialization.jsonObject(with: transport.requests[0].httpBody ?? Data()) as? [String: Any])
        #expect(body["plan"] as? String == "free")
        #expect(body["consent_version"] as? String == "regular-2027-v1")
        #expect(body["accept_beta_terms"] as? Bool == false)
    }

    @Test func debtPaymentCarriesTheIdempotencyKeyAndExactAmount() async throws {
        let transport = ScriptedTransport([.status(200, #"{"status":"ok","debt_id":7,"payment_amount":1234.56,"new_remaining_amount":0}"#)])
        let result = try await LiveDincrService(client: client(transport))
            .payDebt(id: 7, amount: Decimal(string: "1234.56")!, idempotencyKey: "op_abcdef12")
        #expect(result.newRemainingAmount == 0)
        let request = transport.requests[0]
        #expect(request.url?.path == "/user-product/finance/debts/7/payments")
        #expect(request.value(forHTTPHeaderField: "X-Idempotency-Key") == "op_abcdef12")
        let text = String(decoding: request.httpBody ?? Data(), as: UTF8.self)
        #expect(text.contains("1234.56"))
    }

    @Test func invalidAmountsNeverLeaveTheDevice() async throws {
        let service = LiveDincrService(client: client(ScriptedTransport([])))
        for amount in [Decimal(0), Decimal(-5), Decimal(string: "0.001")!, Decimal(string: "10000000000")!] {
            await #expect(throws: APIError.self) {
                _ = try await service.payDebt(id: 1, amount: amount, idempotencyKey: "op_abcdef12")
            }
            await #expect(throws: APIError.self) {
                _ = try await service.contribute(goalID: 1, GoalContribution(amount: amount, contributionDate: nil), idempotencyKey: "op_abcdef12")
            }
        }
        await #expect(throws: APIError.self) {
            _ = try await service.contribute(goalID: 1, GoalContribution(amount: 10, contributionDate: "2026-02-30"), idempotencyKey: "op_abcdef12")
        }
        #expect(throws: Never.self) { try WriteContract.checkAmount(AmountInput.maxAmount) }
    }

    @Test func profileExposesPlanAndLegalFromMe() throws {
        let json = #"{"id":1,"role":"user","subscription":{"plan":"basic","status":"active","access_source":"courtesy"},"legal":{"required":true,"terms_version":"t1","privacy_version":"p1"}}"#
        let profile = try APIClient.decoder.decode(Profile.self, from: Data(json.utf8))
        #expect(profile.planTier == .basic)
        #expect(profile.isCourtesy)
        #expect(profile.legal?.required == true)
        #expect(profile.legal?.termsVersion == "t1")
    }

    // MARK: Fixture semantics (Debug-only stand-in; mirrors backend write semantics)

    @Test func fixtureDebtPaymentIsIdempotentAndCapped() async throws {
        let fixture = FixtureBackend.service(FixtureBackend(scenario: .populated, latency: .zero))
        let debt = try #require(try await fixture.debts().first)
        let first = try await fixture.payDebt(id: debt.id, amount: 1_000, idempotencyKey: "op_same_key")
        let replay = try await fixture.payDebt(id: debt.id, amount: 1_000, idempotencyKey: "op_same_key")
        #expect(first.newRemainingAmount == (debt.remainingAmount ?? 0) - 1_000)
        #expect(replay.newRemainingAmount == first.newRemainingAmount)
        let capped = try await fixture.payDebt(id: debt.id, amount: AmountInput.maxAmount, idempotencyKey: "op_other_key")
        #expect(capped.newRemainingAmount == 0)
    }

    @Test func fixturePaidPlanWithoutPromotionIsRefused() async throws {
        let fixture = FixtureBackend.service(FixtureBackend(scenario: .choosePlan, latency: .zero))
        #expect(try await fixture.me().planSelected == false)
        await #expect(throws: APIError.self) { _ = try await fixture.choosePlan(PlanChangeRequest(plan: "vip")) }
        let result = try await fixture.choosePlan(PlanChangeRequest(plan: "free"))
        #expect(result.profile?.planSelected == true)
    }
}
