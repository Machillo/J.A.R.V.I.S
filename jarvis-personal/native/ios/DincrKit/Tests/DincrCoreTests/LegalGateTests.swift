import Foundation
import Testing
@testable import DincrCore

/// SEC-01 — the server's legal gate answers 403 `legal_acceptance_required` (`auth/legal.py`). The
/// client keeps that code so the app can bring back the acceptance screen, and the fixture used by
/// the UI tests behaves like the server. Android: `LegalGateTest.kt`.
@Suite struct LegalGateTests {
    @Test func theGatesCodeReachesTheApp() {
        let body = Data(#"{"detail":{"code":"legal_acceptance_required","message":"Antes de continuar, aceptá los Términos y la Política de Privacidad vigentes."}}"#.utf8)
        let error = APIError.from(status: 403, body: body, language: .spanish, requestID: nil)
        #expect(error.code == APIError.legalAcceptanceRequiredCode)
        #expect(error.message.hasPrefix("Antes de continuar"))
    }

    @Test func afterTheTermsChangeWritesWaitForAcceptanceAndReadsDoNot() async throws {
        let backend = FixtureBackend(latency: .zero, language: .spanish, legalLapses: true)
        let service = FixtureBackend.service(backend)
        #expect(try await service.debts().isEmpty == false, "reads are not held back")
        await #expect(throws: APIError.self) { _ = try await service.payDebt(id: 31, amount: 1000, idempotencyKey: "pay-1") }
        let profile = try await service.me()
        #expect(profile.legal?.required == true, "the identity asks for acceptance again")
        await #expect(throws: APIError.self) { _ = try await service.payDebt(id: 31, amount: 1000, idempotencyKey: "pay-2") }

        let legal = try #require(profile.legal)
        _ = try await service.acceptLegal(LegalAcceptRequest(termsVersion: legal.termsVersion ?? "", privacyVersion: legal.privacyVersion ?? ""))
        #expect(try await service.me().legal?.required == false)
        _ = try await service.payDebt(id: 31, amount: 1000, idempotencyKey: "pay-3")
    }

    @Test func withoutTheLapseNothingChanges() async throws {
        let service = FixtureBackend.service(FixtureBackend(latency: .zero, language: .spanish))
        _ = try await service.payDebt(id: 31, amount: 1000, idempotencyKey: "pay-1")
        #expect(try await service.me().legal?.required == false)
    }
}
