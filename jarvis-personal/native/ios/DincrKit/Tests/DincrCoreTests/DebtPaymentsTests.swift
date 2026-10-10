import Foundation
import Testing
@testable import DincrCore

/// DEB-07a — a debt's payment history: the backend's shape decodes, and the fixture records each
/// payment with the amount actually applied (capped at the balance), newest first. Android:
/// `DebtPaymentsTest.kt`. Synthetic data.
@Suite struct DebtPaymentsTests {
    @Test func aPaymentDecodesTheBackendsShape() throws {
        let json = #"[{"id":7,"payment_date":"2026-10-09","amount":70000.0},{"id":3,"payment_date":"2026-10-01","amount":null}]"#
        let payments = try APIClient.decoder.decode([DebtPayment].self, from: Data(json.utf8))
        #expect(payments.map(\.id) == [7, 3])
        #expect(payments.first?.paymentDate == "2026-10-09" && payments.first?.amount == 70000)
        #expect(payments.last?.amount == nil, "an unknown amount stays unknown")
    }

    @Test func theFixtureListsEachPaymentNewestFirstWithTheAmountApplied() async throws {
        let service = FixtureBackend.service(FixtureBackend(scenario: .populated, latency: .zero))
        let debt = try #require(try await service.debts().first { ($0.remainingAmount ?? 0) > 0 })
        let remaining = try #require(debt.remainingAmount)
        #expect(try await service.debtPayments(id: debt.id).isEmpty)
        _ = try await service.payDebt(id: debt.id, amount: 1000, idempotencyKey: "pay-1")
        _ = try await service.payDebt(id: debt.id, amount: remaining * 2, idempotencyKey: "pay-2")
        let payments = try await service.debtPayments(id: debt.id)
        #expect(payments.map(\.amount) == [remaining - 1000, 1000], "newest first; the second payment is capped at the balance")
    }
}
