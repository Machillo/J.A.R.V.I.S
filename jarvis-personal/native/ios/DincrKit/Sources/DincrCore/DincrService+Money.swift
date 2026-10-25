import Foundation

// JARVIS → Mi dinero (Owner only: `/finance/*` is an Owner route and the backend refuses everyone
// else). The reads never write; saving or removing an account is an explicit Owner command, never
// retried on its own.
extension DincrService {
    /// The current cycle: expected and received income, the statement period's spending and the real balance.
    public func cycleReport() async throws -> CycleReport { try await client.get("/finance/cycle-report") }

    /// The Owner's active accounts and their real total.
    public func accountBalances() async throws -> AccountBalances { try await client.get("/finance/account-balances") }

    /// Creates the account, or updates the one with the same name and last 4 digits, with this balance.
    public func saveAccountBalance(_ request: AccountBalanceRequest) async throws {
        let _: Acknowledgement = try await client.send("POST", "/finance/account-balances", body: request)
    }

    /// Removes the account from the Owner's accounts (the backend deactivates it).
    public func removeAccountBalance(id: Int) async throws {
        let _: Acknowledgement = try await client.send("DELETE", "/finance/account-balances/\(id)")
    }
}
