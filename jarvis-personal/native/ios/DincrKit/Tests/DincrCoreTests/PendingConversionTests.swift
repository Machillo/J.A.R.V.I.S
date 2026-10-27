import Foundation
import Testing
@testable import DincrCore

/// Dollar expenses that wait for the close: a request asks for it only when the editor says so, the
/// colones list leaves them out (never ₡0), and the pending listing totals them per currency
/// (Android: `PendingConversionTest`).
@Suite struct PendingConversionTests {
    private func json(_ value: some Encodable) throws -> [String: Any] {
        try JSONSerialization.jsonObject(with: APIClient.encoder.encode(value)) as? [String: Any] ?? [:]
    }

    private func hotel(amount: Decimal = 120, waits: Bool = true, rate: Decimal? = nil) -> EntryCreate {
        EntryCreate(amount: amount, description: "Hotel", category: "Compras", entryDate: "2026-10-12", currency: "USD",
                    exchangeRate: rate, convertAtClose: waits)
    }

    @Test func theRequestAsksToWaitOnlyWhenTold() throws {
        #expect(try json(hotel())["convert_at_close"] as? Bool == true)
        #expect(try json(hotel(waits: false, rate: 500)).keys.contains("convert_at_close") == false)
        let edit = MovementUpdate(transactionDate: "2026-10-12", description: "Hotel", amount: 150, transactionType: .expense,
                                  category: "Compras", currency: "USD", convertAtClose: true)
        #expect(try json(edit)["convert_at_close"] as? Bool == true)
        #expect(try json(edit).keys.contains("exchange_rate") == false)
    }

    @Test func thePendingListingDecodesWithItsTotals() throws {
        let body = #"""
        {"status":"ok","available":true,"items":[{"movement_id":"expense:9","id":9,"entry_date":"2026-10-12","description":"Hotel",
          "category":"Compras","original_amount":120.5,"original_currency":"USD","financial_account_id":null}],
         "totals":[{"currency":"USD","amount":120.5,"count":1}]}
        """#
        let pending = try APIClient.decoder.decode(PendingConversion.self, from: Data(body.utf8))
        #expect(pending.available && pending.items.first?.originalAmount == Decimal(string: "120.5"))
        #expect(pending.totals == [PendingConversion.Total(currency: "USD", amount: Decimal(string: "120.5")!, count: 1)])
    }

    @Test func theFixtureKeepsDollarsApartUntilConverted() async throws {
        let service = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero))
        let colones = try await service.movements()
        try await service.create(.expense, hotel(), idempotencyKey: IdempotencyKey.new())
        try await service.create(.expense, hotel(amount: Decimal(string: "30.5")!), idempotencyKey: IdempotencyKey.new())
        #expect(try await service.movements() == colones)  // never a ₡0 row
        let pending = try await service.pendingConversion()
        #expect(pending.items.count == 2)
        #expect(pending.totals == [PendingConversion.Total(currency: "USD", amount: Decimal(string: "150.5")!, count: 2)])
        // The user converts one with their own rate: it joins the colones list and leaves the pending one.
        let first = try #require(pending.items.first)
        try await service.update(movementID: first.movementId, MovementUpdate(transactionDate: first.entryDate, description: "Hotel", amount: first.originalAmount,
                                                                              transactionType: .expense, category: "Compras", currency: "USD", exchangeRate: 500))
        #expect(try await service.pendingConversion().items.count == 1)
        #expect(try await service.movements().contains { $0.movementId == first.movementId })
    }

    @Test func onlyADollarExpenseWithoutARateCanWait() async throws {
        let service = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero))
        await #expect(throws: APIError.self) { try await service.create(.expense, hotel(rate: 500), idempotencyKey: IdempotencyKey.new()) }
        await #expect(throws: APIError.self) {
            try await service.create(.income, hotel(), idempotencyKey: IdempotencyKey.new())
        }
        #expect(try await service.pendingConversion().items.isEmpty)
    }
}
