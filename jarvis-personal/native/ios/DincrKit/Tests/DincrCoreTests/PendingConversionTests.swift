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
        #expect(pending.totals == [PendingConversion.Total(currency: "USD", amount: Decimal(string: "150.5")!, count: 2, estimatedAmount: 75_250)])
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

    // MARK: The close (3d)

    private static let october22 = FixtureBackend.utc.date(from: DateComponents(year: 2026, month: 10, day: 22))!

    private func expense(_ description: String, _ amount: Decimal, on day: String, card: Int? = nil) -> EntryCreate {
        EntryCreate(amount: amount, description: description, category: "Compras", entryDate: day, currency: "USD",
                    financialAccountId: card, convertAtClose: true)
    }

    @Test func pendingExpensesAreGroupedByCardCutOrMonth() async throws {
        let service = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero, today: Self.october22))
        try await service.setStatementCutDay(id: 2, day: 21)
        try await service.create(.expense, expense("Hotel", 120, on: "2026-10-12", card: 2), idempotencyKey: IdempotencyKey.new())
        try await service.create(.expense, expense("Taxi", 30, on: "2026-10-25", card: 2), idempotencyKey: IdempotencyKey.new())
        try await service.create(.expense, expense("Propina", 5, on: "2026-10-03"), idempotencyKey: IdempotencyKey.new())
        let periods = try await service.pendingConversion().periods
        #expect(periods.map(\.key) == ["card:2:2026-10-21", "month:2026-10", "card:2:2026-11-21"])
        #expect(periods.map(\.closable) == [true, false, false])
        #expect(periods.first?.start == "2026-09-22" && periods.first?.totals.first?.amount == 120)
    }

    @Test func aCloseConvertsItsPeriodWithOneRateOnce() async throws {
        let service = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero, today: Self.october22))
        try await service.setStatementCutDay(id: 2, day: 21)
        try await service.create(.expense, expense("Hotel", 120, on: "2026-10-12", card: 2), idempotencyKey: IdempotencyKey.new())
        try await service.create(.expense, expense("Taxi", 30, on: "2026-10-25", card: 2), idempotencyKey: IdempotencyKey.new())
        let result = try await service.closePending(PendingClose(periodKey: "card:2:2026-10-21", exchangeRate: 510), idempotencyKey: IdempotencyKey.new())
        #expect(result.converted == 1 && result.amount == 61_200 && result.currency == "CRC")
        #expect(try await service.pendingConversion().items.map(\.description) == ["Taxi"])
        let hotel = try #require(try await service.movements().first { $0.description == "Hotel" })
        #expect(hotel.amount == 61_200 && hotel.exchangeRate == 510 && hotel.originalAmount == 120)
        await #expect(throws: APIError.self) {  // closed once; the next cycle has not ended
            _ = try await service.closePending(PendingClose(periodKey: "card:2:2026-10-21", exchangeRate: 600), idempotencyKey: IdempotencyKey.new())
        }
        await #expect(throws: APIError.self) {
            _ = try await service.closePending(PendingClose(periodKey: "card:2:2026-11-21", exchangeRate: 600), idempotencyKey: IdempotencyKey.new())
        }
    }

    @Test func aServerWithoutTheCloseSendsNoPeriods() throws {
        let body = #"{"status":"ok","available":true,"items":[],"totals":[]}"#
        #expect(try APIClient.decoder.decode(PendingConversion.self, from: Data(body.utf8)).periods.isEmpty)
    }
}

/// The estimate of the waiting dollars: what Gastos adds on screen. Synthetic data only.
struct PendingEstimateTests {
    private func item(_ id: Int, _ day: String, _ text: String, estimate: Decimal?) -> PendingConversion.Item {
        .init(movementId: "expense:\(id)", id: id, entryDate: day, description: text, category: nil, originalAmount: 10,
              originalCurrency: "USD", financialAccountId: nil, estimatedAmount: estimate)
    }

    private var pending: PendingConversion {
        PendingConversion(available: true, items: [item(1, "2026-11-02", "Café", estimate: 5_000), item(2, "2026-11-20", "Libro", estimate: 6_000),
                                                   item(3, "2026-10-05", "Viaje", estimate: 7_000), item(4, "2026-11-25", "Sin tasa", estimate: nil)], totals: [])
    }

    @Test func onlyTheMonthOnScreenCounts() {
        #expect(pending.estimate(month: "2026-11", query: "") == PendingEstimate(sum: 11_000, withoutEstimate: 1))
        #expect(pending.estimate(month: "2026-10", query: "") == PendingEstimate(sum: 7_000, withoutEstimate: 0))
    }

    @Test func aSearchLooksThroughEveryMonth() {
        #expect(pending.estimate(month: "2026-11", query: "viaje") == PendingEstimate(sum: 7_000, withoutEstimate: 0))
    }

    @Test func noEstimateIsUnknownNotZero() {
        #expect(pending.estimate(month: "2026-09", query: "") == PendingEstimate(sum: nil, withoutEstimate: 0))
        #expect(pending.estimate(month: "2026-11", query: "sin tasa") == PendingEstimate(sum: nil, withoutEstimate: 1))
        let none = MovementTotals(income: 5, expenses: nil, debtPaid: nil)
        #expect(none.addingEstimate(nil).expenses == nil, "nothing to add keeps an unknown side unknown")
    }

    @Test func theEstimateCountsInExpensesAndTheResult() {
        let totals = MovementTotals(income: 100, expenses: 30, debtPaid: nil).addingEstimate(20)
        #expect(totals.expenses == 50 && totals.result == 50)
        #expect(MovementTotals(income: nil, expenses: nil, debtPaid: nil).addingEstimate(20).expenses == 20)
    }

    @Test func oneExpenseWithoutARateDoesNotHideTheOthersOnHoy() {
        #expect(pending.estimateOfAll == PendingEstimate(sum: 18_000, withoutEstimate: 1))
    }

    @Test func aReadOnlySalaryRowDecodesAndCannotBeEdited() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let row = try decoder.decode(Movement.self, from: Data(#"{"movement_id":"salary_estimate:2026-11","source_id":null,"origin":"salary_estimate","transaction_date":"2026-11-01","description":"Salario del mes (estimado)","amount":400000,"transaction_type":"income","category":"Salario","editable":false,"counts_in":"income"}"#.utf8))
        #expect(row.transactionType == .income && !row.canEdit(entryCurrencies: ["USD"]))
        #expect(MovementTotals([row]).income == 400_000)
    }

    @Test func anOlderServerPromisesNothing() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let old = try decoder.decode(PendingConversion.self, from: Data(#"{"available":true,"items":[],"totals":[{"currency":"USD","amount":5,"count":1}]}"#.utf8))
        #expect(!old.autoClose && old.totals[0].estimatedAmount == nil)
        let new = try decoder.decode(PendingConversion.self, from: Data(#"{"available":true,"items":[],"totals":[{"currency":"USD","amount":5,"count":1,"estimated_amount":2500}],"auto_close":true}"#.utf8))
        #expect(new.autoClose && new.totals[0].estimatedAmount == 2_500)
    }
}
