import Foundation

// JARVIS → Patrimonio (Owner only: `/finance/*` is an Owner route and the backend refuses everyone
// else). The reads never write. The writes are explicit Owner commands, never retried on their own:
// the backend does not deduplicate them.
extension DincrService {
    /// The latest portfolio snapshot, its positions and the money reserved to invest. A read: it never syncs.
    public func investmentCenter() async throws -> InvestmentCenter { try await client.get("/finance/investment-center") }

    /// Asks the server to refresh the snapshot from IBKR (an external call that can fail).
    public func syncIbkr() async throws {
        let _: IbkrSyncResult = try await client.send("POST", "/finance/investment-center/sync-ibkr")
    }

    /// The Owner's businesses, their movements and the totals.
    public func businessCenter() async throws -> BusinessCenter { try await client.get("/finance/business-center") }

    public func createBusiness(_ request: BusinessCreateRequest) async throws {
        let _: BusinessWriteResult = try await client.send("POST", "/finance/business-center/businesses", body: request)
    }

    /// Records a business movement; an income or expense also creates a transaction in the Owner's ledger.
    public func addBusinessMovement(_ request: BusinessMovementRequest) async throws {
        let _: BusinessWriteResult = try await client.send("POST", "/finance/business-center/movements", body: request)
    }
}
