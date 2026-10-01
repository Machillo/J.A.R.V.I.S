import Foundation

// Plan tab (Estrategia, Distribución, Salvavidas), Cuentas and the Owner's analysis. Same rules as
// the rest of `DincrService`: one method per backend route, every figure computed by the backend.
extension DincrService {
    // MARK: Strategy (three contracts: Basic ≠ VIP Users ≠ Owner)

    /// VIP Users: the neutral dashboard (`strategy.scope == "users"`).
    public func strategyDashboard() async throws -> StrategyDashboard { try await client.get("/user-product/vip/strategy-dashboard") }

    /// Owner only (an owner/admin route). Never called for another role: `StrategySource` decides
    /// from the server role, and the backend refuses everyone else.
    public func ownerStrategyDashboard() async throws -> StrategyDashboard { try await client.get("/jarvis/premium/strategy-dashboard") }

    /// The strategy the identity reads; Estrategia and Distribución show the same answer.
    public func planStrategy(_ source: StrategySource) async throws -> PlanStrategy {
        switch source {
        case .basic: return .basic(try await strategyBasic())
        case .usersDashboard: return .dashboard(try await strategyDashboard())
        case .ownerDashboard: return .dashboard(try await ownerStrategyDashboard())
        case .unavailable: throw APIError(kind: .forbidden, message: AppLanguage.current.pick("Esta función no está incluida en tu plan.", "This feature isn’t included in your plan."))
        }
    }

    // MARK: Salvavidas (VIP; the Owner by role)

    public func salvavidas() async throws -> Salvavidas { try await client.get("/user-product/vip/salvavidas") }

    /// One change per request. Months must be one of 1/3/6 and an amount must fit NUMERIC(12,2);
    /// anything else never leaves the device.
    public func updateSalvavidas(_ update: SalvavidasUpdate) async throws -> Salvavidas {
        if let months = update.targetMonths, !Salvavidas.defaultTargetMonths.contains(months) { throw WriteContract.invalid }
        if let amount = update.currentAmount { try WriteContract.checkAmount(amount, allowZero: true) }
        if update.targetMonths == nil && update.currentAmount == nil && update.protectedExpenseIds == nil { throw WriteContract.invalid }
        return try await client.send("PUT", "/user-product/vip/salvavidas", body: update)
    }

    // MARK: Cuentas: the same review inbox, filtered (VIP and `gmail_automation`)

    /// Every reviewed state and pending notices of one bank (`bank` is matched by name on the server).
    public func mailCandidates(bank: String) async throws -> [MailCandidate] {
        let list: MailCandidateList = try await client.get("/user-product/vip/gmail/emails", query: [URLQueryItem(name: "bank", value: bank)])
        return list.items ?? []
    }

    /// Every notice of one detected account.
    public func mailCandidates(financialAccountID: Int) async throws -> [MailCandidate] {
        let list: MailCandidateList = try await client.get("/user-product/vip/gmail/emails", query: [URLQueryItem(name: "financial_account_id", value: String(financialAccountID))])
        return list.items ?? []
    }

    // MARK: JARVIS · Análisis financiero (Owner only; owner/admin routes)

    public func transactionAnalysis() async throws -> TransactionAnalysis { try await client.get("/transactions/analysis/summary") }

    /// Note: the backend stores a net-worth snapshot when this report is read (historical behavior).
    public func netWorth() async throws -> NetWorthReport { try await client.get("/finance/net-worth") }

    public func financialEngine() async throws -> FinancialEngineReport { try await client.get("/finance/engine") }

    /// The three answers together; one failure fails the screen (it offers a retry).
    public func ownerAnalysis() async throws -> OwnerAnalysis {
        async let analysis = self.transactionAnalysis()
        async let worth = self.netWorth()
        async let report = self.financialEngine()
        return OwnerAnalysis(transactions: try await analysis, netWorth: try await worth, engine: try await report)
    }
}
