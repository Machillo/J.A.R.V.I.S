import Foundation
import Testing
@testable import DincrCore

/// Own accounts from the app: "Es mía / No es mía / No la reconozco" and an own account no notice came
/// from. "No la reconozco" travels as `pending` (never an own account) and comes back with its review
/// date; only the last 4 digits ever leave the device. Android: `OwnAccountsTest`.
@Suite struct OwnAccountsTests {
    private func body(_ request: URLRequest) throws -> [String: Any] {
        try #require(JSONSerialization.jsonObject(with: request.httpBody ?? Data()) as? [String: Any])
    }

    @Test func eachAnswerTravelsAsTheBackendsStatus() async throws {
        for (answer, wire) in [(AccountOwnership.own, "own"), (.notMine, "not_mine"), (.unknown, "pending")] {
            let transport = ScriptedTransport([.status(200, #"{"status":"ok"}"#)])
            let service = DincrService(client: APIClient(baseURL: URL(string: "https://api.example.test")!, tokens: CountingTokens(),
                                                         transport: transport, language: .spanish, backoff: { _ in }))
            try await service.setAccountOwnership(id: 7, answer)
            let request = try #require(transport.requests.first)
            #expect(request.httpMethod == "PUT" && request.url?.path == "/user-product/vip/financial-identity/accounts/7")
            #expect(try body(request)["ownership_status"] as? String == wire)
        }
    }

    @Test func notRecognisedIsAReviewedPendingAccountNotAnUnansweredOne() {
        func account(_ status: String?, _ reviewed: String?) -> FinancialIdentity.Account {
            .init(id: 1, accountName: nil, bankName: nil, currency: "CRC", accountLast4: "4560", ownershipStatus: status, ownershipConfirmedAt: reviewed)
        }
        #expect(account("pending", nil).ownership == nil)
        #expect(account("pending", "2026-10-21T12:00:00Z").ownership == .unknown)
        #expect(account("own", "2026-10-21T12:00:00Z").ownership == .own)
        #expect(account("not_mine", nil).ownership == .notMine)
    }

    @Test func aDeclarationSendsOnlyTheLastFourDigits() async throws {
        let declaration = OwnAccountDeclaration(institutionCode: "multimoney", accountLast4: "6281", currency: "USD")
        #expect(declaration.isComplete)
        let transport = ScriptedTransport([.status(200, #"{"status":"ok","item":{"id":9,"account_last4":"6281","currency":"USD","ownership_status":"own"}}"#)])
        let service = DincrService(client: APIClient(baseURL: URL(string: "https://api.example.test")!, tokens: CountingTokens(),
                                                     transport: transport, language: .spanish, backoff: { _ in }))
        let item = try await service.declareOwnAccount(declaration)
        #expect(item?.ownership == .own && item?.accountLast4 == "6281")
        let sent = try body(try #require(transport.requests.first))
        #expect(sent["institution_code"] as? String == "multimoney" && sent["account_last4"] as? String == "6281" && sent["currency"] as? String == "USD")
        #expect(sent["institution_name"] == nil, "only 'other' carries a name")
    }

    @Test func anIncompleteDeclarationIsNotSent() {
        #expect(!OwnAccountDeclaration(institutionCode: "bac", accountLast4: "612", currency: "CRC").isComplete)
        #expect(!OwnAccountDeclaration(institutionCode: "bac", accountLast4: "61a1", currency: "CRC").isComplete)
        #expect(!OwnAccountDeclaration(institutionCode: "other", institutionName: "  ", accountLast4: "6121", currency: "CRC").isComplete)
        #expect(!OwnAccountDeclaration(institutionCode: "bac", accountLast4: "6121", currency: "EUR").isComplete)
        #expect(OwnAccountDeclaration(institutionCode: "other", institutionName: "Coopealianza", accountLast4: "6121", currency: "CRC").isComplete)
    }

    @Test func theFixtureKeepsDecisionsAndReusesADeclaredAccount() async throws {
        let backend = FixtureBackend(plan: .vip, latency: .zero, language: .spanish)
        let service = FixtureBackend.service(backend)
        let first = try #require(try await service.declareOwnAccount(OwnAccountDeclaration(institutionCode: "multimoney", accountLast4: "6281", currency: "USD")))
        let again = try #require(try await service.declareOwnAccount(OwnAccountDeclaration(institutionCode: "multimoney", accountLast4: "6281", currency: "USD")))
        #expect(first.id == again.id)
        try await service.setAccountOwnership(id: 1, .unknown)
        let items = try await service.financialIdentity().items ?? []
        #expect(items.first { $0.id == 1 }?.ownership == .unknown)
        #expect(items.first { $0.id == first.id }?.ownership == .own)
    }
}
