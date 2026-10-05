import Foundation
import Testing
@testable import DincrCore

/// UX-4 — debts are managed in Plan → Deudas. Opening them reads the list and nothing else, and a
/// percentage the backend can't know (no original amount) is never shown as 0 % paid. Android:
/// `DebtsInPlanTest.kt`.
@Suite struct DebtsInPlanTests {
    private func service(_ transport: ScriptedTransport) -> DincrService {
        DincrService(client: APIClient(baseURL: URL(string: "https://api.example.test")!, tokens: CountingTokens(), transport: transport, language: .spanish, backoff: { _ in }))
    }

    @Test func openingDebtsOnlyReadsTheList() async throws {
        let list = #"[{"id":7,"name":"Tarjeta","debt_type":"credit_card","total_amount":500000,"remaining_amount":300000,"monthly_payment":45000,"progress_percent":40.0}]"#
        let transport = ScriptedTransport([.status(200, list)])
        let debts = try await service(transport).debts()
        #expect(debts.count == 1)
        #expect(transport.requests.count == 1)
        #expect(transport.requests.first?.httpMethod == "GET")
        #expect(transport.requests.first?.url?.path.hasSuffix("/finance/debts") == true)
        // No payment, no installment application, no other write.
        #expect(!transport.requests.contains { ($0.url?.path ?? "").contains("payments") || ($0.url?.path ?? "").contains("apply-due-installments") })
    }

    @Test func progressIsShownOnlyFromAKnownOriginalAmount() throws {
        let known = try APIClient.decoder.decode(Debt.self, from: Data(#"{"id":1,"total_amount":500000,"remaining_amount":300000,"progress_percent":40.0}"#.utf8))
        #expect(known.knownProgressPercent == 40)
        // The list answers 0 % when the original amount is unknown: that is not a fact about the debt.
        let unknownTotal = try APIClient.decoder.decode(Debt.self, from: Data(#"{"id":2,"total_amount":null,"remaining_amount":300000,"progress_percent":0}"#.utf8))
        #expect(unknownTotal.knownProgressPercent == nil)
        let zeroTotal = try APIClient.decoder.decode(Debt.self, from: Data(#"{"id":3,"total_amount":0,"remaining_amount":0,"progress_percent":0}"#.utf8))
        #expect(zeroTotal.knownProgressPercent == nil)
        let paidOff = try APIClient.decoder.decode(Debt.self, from: Data(#"{"id":4,"total_amount":100,"remaining_amount":0,"progress_percent":100}"#.utf8))
        #expect(paidOff.knownProgressPercent == 100)
    }

    @Test func unknownFiguresStayUnknown() throws {
        let debt = try APIClient.decoder.decode(Debt.self, from: Data(#"{"id":5,"name":"Préstamo","remaining_amount":null}"#.utf8))
        #expect(debt.remainingAmount == nil)
        #expect(debt.monthlyPayment == nil)
        #expect(debt.nextPaymentDate == nil)
    }
}
