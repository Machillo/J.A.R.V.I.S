import Foundation
import Testing
@testable import DincrCore

/// "Pagado con" on manual expenses: a create sends the account only when chosen, an edit leaves the
/// stored link alone unless it is changed (null clears it), and only own accounts are offered
/// (Android: `PaidWithTest`).
@Suite struct PaidWithTests {
    private func json(_ value: some Encodable) throws -> [String: Any] {
        try JSONSerialization.jsonObject(with: APIClient.encoder.encode(value)) as? [String: Any] ?? [:]
    }

    private func update(_ change: PaidWithChange) -> MovementUpdate {
        MovementUpdate(transactionDate: "2026-10-20", description: "Almuerzo", amount: 4500, transactionType: .expense, category: "Comida", paidWith: change)
    }

    @Test func anEditSendsTheKeyOnlyWhenTheLinkChanges() throws {
        #expect(try json(update(.unchanged)).keys.contains("financial_account_id") == false)
        #expect(try json(update(.set(2)))["financial_account_id"] as? Int == 2)
        let cleared = try json(update(.set(nil)))
        #expect(cleared.keys.contains("financial_account_id") && cleared["financial_account_id"] is NSNull)
    }

    @Test func aCreateSendsTheAccountOnlyWhenChosen() throws {
        #expect(try json(EntryCreate(amount: 4500, description: "Almuerzo", category: "Comida", entryDate: nil)).keys.contains("financial_account_id") == false)
        #expect(try json(EntryCreate(amount: 4500, description: "Almuerzo", category: "Comida", entryDate: nil, financialAccountId: 2))["financial_account_id"] as? Int == 2)
    }

    @Test func nothingIsOfferedWhileUnavailable() throws {
        let json = #"{"status":"ok","available":false,"items":[{"id":2,"account_name":"Tarjeta","bank_name":"BAC","account_type":"credit_card","account_last4":"5678","currency":"USD"}]}"#
        let options = try APIClient.decoder.decode(PaidWithOptions.self, from: Data(json.utf8))
        #expect(options.offered.isEmpty)
        #expect(options.items.first?.label == "BAC · Tarjeta ••5678")
    }

    @Test func theFixtureLinksOnlyOwnAccountsAndKeepsTheLinkUnlessTold() async throws {
        let service = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero))
        let options = try await service.paidWithOptions()
        let card = try #require(options.offered.first)
        #expect(card.isCard && options.offered.allSatisfy { $0.id != 1 })  // the pending account is not offered
        try await service.create(.expense, EntryCreate(amount: 4500, description: "Almuerzo con tarjeta", category: "Comida", entryDate: "2026-10-20",
                                                       financialAccountId: card.id), idempotencyKey: IdempotencyKey.new())
        let created = try #require(try await service.movements().first { $0.description == "Almuerzo con tarjeta" })
        #expect(created.financialAccountId == card.id)
        try await service.update(movementID: created.movementId, MovementUpdate(transactionDate: "2026-10-20", description: "Almuerzo con tarjeta",
                                                                                amount: 5000, transactionType: .expense, category: "Comida"))
        #expect(try await service.movements().first { $0.movementId == created.movementId }?.financialAccountId == card.id)
        try await service.update(movementID: created.movementId, MovementUpdate(transactionDate: "2026-10-20", description: "Almuerzo con tarjeta",
                                                                                amount: 5000, transactionType: .expense, category: "Comida", paidWith: .set(nil)))
        #expect(try await service.movements().first { $0.movementId == created.movementId }?.financialAccountId == nil)
        await #expect(throws: APIError.self) {
            try await service.create(.expense, EntryCreate(amount: 1, description: "x", category: "Comida", entryDate: nil, financialAccountId: 1),
                                     idempotencyKey: IdempotencyKey.new())
        }
    }
}
