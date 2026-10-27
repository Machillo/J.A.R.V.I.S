import Foundation

// JARVIS → Registros (Owner only: `/finance/*` is an Owner route and the backend refuses everyone
// else). The reads never write; confirming a balance is an explicit Owner command, never retried
// on its own.
extension DincrService {
    /// The known incomes and obligations of the next `days` days and the balance they leave.
    public func moneyTimeline(days: Int = 45) async throws -> MoneyTimeline {
        try await client.get("/finance/timeline", query: [URLQueryItem(name: "days", value: String(days))])
    }

    /// Each tracked account's expected balance (declared + movements since) against its real one.
    public func reconciliation() async throws -> Reconciliation { try await client.get("/finance/reconciliation") }

    /// Stores the real balance the Owner checked as the account's new declared balance.
    public func confirmReconciliation(accountID: Int, _ request: ReconciliationConfirmRequest) async throws {
        let _: ReconciliationConfirmResult = try await client.send("POST", "/finance/reconciliation/\(accountID)/confirm", body: request)
    }
}
