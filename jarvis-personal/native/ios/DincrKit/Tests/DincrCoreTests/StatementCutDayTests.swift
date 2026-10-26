import Foundation
import Testing
@testable import DincrCore

/// A credit card's statement cut day (Cuentas): only own credit cards take one, a cleared day is an
/// explicit null, and the server's "not available yet" is kept (Android: `StatementCutDayTest`).
@Suite struct StatementCutDayTests {
    @Test func theRequestAlwaysSendsTheKeyEvenToClearIt() throws {
        let set = try JSONSerialization.jsonObject(with: APIClient.encoder.encode(StatementCutDayRequest(21))) as? [String: Any]
        #expect(set?["statement_cut_day"] as? Int == 21)
        let cleared = try JSONSerialization.jsonObject(with: APIClient.encoder.encode(StatementCutDayRequest(nil))) as? [String: Any]
        #expect(cleared?.keys.contains("statement_cut_day") == true && cleared?["statement_cut_day"] is NSNull)
    }

    @Test func theListingCarriesTheDayAndWhetherItIsAvailable() throws {
        let json = #"{"status":"ok","statement_cut_day_available":false,"items":[{"id":2,"account_type":"credit_card","ownership_status":"own","statement_cut_day":null}]}"#
        let identity = try APIClient.decoder.decode(FinancialIdentity.self, from: Data(json.utf8))
        #expect(identity.statementCutDayAvailable == false)
        #expect(identity.items?.first?.statementCutDay == nil && identity.items?.first?.takesCutDay == true)
    }

    @Test func onlyOwnCreditCardsTakeACutDay() {
        func account(_ type: String, _ ownership: String) -> FinancialIdentity.Account {
            FinancialIdentity.Account(id: 1, accountName: nil, bankName: nil, currency: nil, accountLast4: nil, ownershipStatus: ownership, accountType: type)
        }
        #expect(account("credit_card", "own").takesCutDay)
        #expect(!account("credit_card", "pending").takesCutDay)
        #expect(!account("checking", "own").takesCutDay)
    }

    @Test func theFixtureSetsAndClearsItOnOwnCardsOnly() async throws {
        let service = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero))
        let items = try await service.financialIdentity().items ?? []
        let card = try #require(items.first { $0.takesCutDay })
        try await service.setStatementCutDay(id: card.id, day: 21)
        #expect(try await service.financialIdentity().items?.first { $0.id == card.id }?.statementCutDay == 21)
        try await service.setStatementCutDay(id: card.id, day: nil)
        #expect(try await service.financialIdentity().items?.first { $0.id == card.id }?.statementCutDay == nil)
        let notACard = try #require(items.first { $0.accountType != "credit_card" })
        await #expect(throws: APIError.self) { try await service.setStatementCutDay(id: notACard.id, day: 21) }
    }
}
