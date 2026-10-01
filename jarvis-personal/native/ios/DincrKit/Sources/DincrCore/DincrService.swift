import Foundation

/// The DINCR API as the native app uses it: one method per FastAPI route consumed by the Capacitor
/// app (parity IDs in docs/native/PARITY_MATRIX.md). There is one implementation: in Debug fixture
/// mode it runs over `FixtureBackend`, an in-memory HTTP transport, so the same requests, headers,
/// errors and JSON decoding are exercised as against the real backend.
///
/// Every write validates its money before sending (`WriteContract`): a value that did not come from
/// `AmountInput` (or is out of NUMERIC(12,2)) never leaves the device.
public struct DincrService: Sendable {
    let client: APIClient

    public init(client: APIClient) { self.client = client }

    // MARK: Identity and account (A5–A11, G8, G9)

    public func me() async throws -> Profile { try await client.get("/auth/me") }

    public func completeProfileSetup(_ setup: ProfileSetup) async throws -> Profile {
        let envelope: ProfileEnvelope = try await client.send("POST", "/auth/profile-setup", body: setup)
        return envelope.profile
    }

    public func acceptLegal(_ request: LegalAcceptRequest) async throws -> LegalAcceptResult {
        try await client.send("POST", "/auth/legal/accept", body: request)
    }

    public func plans() async throws -> [PlanOption] { try await client.get("/auth/plans") }

    public func billingCatalog() async throws -> BillingCatalog { try await client.get("/product-ops/billing/catalog") }

    public func choosePlan(_ request: PlanChangeRequest) async throws -> PlanChangeResult {
        try await client.send("POST", "/auth/plan", body: request)
    }

    /// `DELETE /auth/me`: the backend schedules the deletion; the app then forgets the session.
    public func deleteAccount() async throws {
        let _: Acknowledgement = try await client.send("DELETE", "/auth/me")
    }

    /// `GET /auth/me/export`: the account's data as JSON, handed to the share sheet unparsed.
    public func exportData() async throws -> Data { try await client.getData("/auth/me/export") }

    // MARK: Operations (A1, B4, B7, I1–I3)

    public func featureFlags() async throws -> FeatureFlags { try await client.get("/product-ops/feature-flags") }

    public func health() async throws -> ServiceHealth { try await client.get("/product-ops/health") }

    /// Public route (no session needed); callers fail open.
    public func releasePolicy(version: String) async throws -> ReleasePolicy {
        try await client.getPublic("/product-ops/release-policy", query: [URLQueryItem(name: "platform", value: "ios"), URLQueryItem(name: "version", value: version)])
    }

    /// JARVIS (Owner): one chat message and the engine's answer. A POST: never retried on its own
    /// (a change is saved only after the Owner's "sí", itself a new message).
    public func jarvisChat(_ message: String) async throws -> JarvisChatReply {
        try await client.send("POST", "/jarvis/chat", body: JarvisChatRequest(message: message))
    }

    /// JARVIS agenda (Owner): the historical upcoming events, from today to `days` out, in order.
    public func jarvisUpcomingEvents(days: Int = JarvisAgenda.days) async throws -> [JarvisEvent] {
        let response: JarvisAgendaResponse = try await client.get("/jarvis/calendar/upcoming", query: [URLQueryItem(name: "days", value: String(days))])
        return response.events
    }

    public func supportTickets() async throws -> [SupportTicket] { try await client.get("/product-ops/feedback") }

    public func createSupportTicket(_ request: SupportRequest) async throws -> SupportCreated {
        try await client.send("POST", "/product-ops/feedback", body: request)
    }

    public func resolveTicket(id: Int, resolved: Bool) async throws {
        let _: Acknowledgement = try await client.send("PATCH", "/product-ops/feedback/\(id)/resolution", body: ResolutionRequest(resolved: resolved))
    }

    // MARK: Movements (C1, D1–D7)

    public func freeDashboard() async throws -> FreeDashboard { try await client.get("/user-product/free/dashboard") }

    public func monthlySummary(period: String) async throws -> MonthlySummary {
        try await client.get("/user-product/free/monthly-summary", query: [URLQueryItem(name: "period", value: period)])
    }

    public func movements() async throws -> [Movement] { try await client.get("/user-product/free/movements") }

    /// D3 — `idempotencyKey` identifies one user submission (8–80 of `A-Za-z0-9_-`): sending it again
    /// cannot create a second row.
    public func create(_ kind: Movement.Kind, _ entry: EntryCreate, idempotencyKey: String) async throws {
        try WriteContract.checkAmount(entry.amount)
        if let rate = entry.exchangeRate { try WriteContract.checkRate(rate) }
        if entry.currency != nil, entry.exchangeRate == nil { throw WriteContract.invalid }
        let path = kind == .income ? "/user-product/finance/income" : "/user-product/finance/expenses"
        let _: Acknowledgement = try await client.send("POST", path, body: entry, idempotencyKey: idempotencyKey)
    }

    public func update(movementID: String, _ update: MovementUpdate) async throws {
        try WriteContract.checkAmount(update.amount)
        try WriteContract.checkDate(update.transactionDate)
        if let rate = update.exchangeRate { try WriteContract.checkRate(rate) }
        if update.currency != nil, update.exchangeRate == nil { throw WriteContract.invalid }
        let _: Acknowledgement = try await client.send("PUT", "/user-product/free/movements/\(Self.encode(movementID))", body: update)
    }

    public func delete(movementID: String) async throws {
        let _: Acknowledgement = try await client.send("DELETE", "/user-product/free/movements/\(Self.encode(movementID))")
    }

    // MARK: Debts (E2–E5)

    public func debts() async throws -> [Debt] { try await client.get("/user-product/finance/debts") }

    public func createDebt(_ request: DebtRequest, idempotencyKey: String) async throws -> Debt {
        try WriteContract.check(request)
        return try await client.send("POST", "/user-product/finance/debts", body: request, idempotencyKey: idempotencyKey)
    }

    /// Needs Basic (`strategy_basic`); the backend answers 403 otherwise.
    public func updateDebt(id: Int, _ request: DebtRequest, idempotencyKey: String) async throws -> Debt {
        try WriteContract.check(request)
        return try await client.send("PUT", "/user-product/finance/debts/\(id)", body: request, idempotencyKey: idempotencyKey)
    }

    public func deleteDebt(id: Int) async throws {
        let _: Acknowledgement = try await client.send("DELETE", "/user-product/finance/debts/\(id)")
    }

    public func payDebt(id: Int, amount: Decimal, idempotencyKey: String) async throws -> DebtPaymentResult {
        try WriteContract.checkAmount(amount)
        return try await client.send("POST", "/user-product/finance/debts/\(id)/payments", body: AmountRequest(amount: amount), idempotencyKey: idempotencyKey)
    }

    // MARK: Goals and savings plans (E6, E7)

    public func goals() async throws -> [Goal] { try await client.get("/user-product/goals") }

    public func createGoal(_ request: GoalRequest, idempotencyKey: String) async throws -> Goal {
        try WriteContract.check(request)
        return try await client.send("POST", "/user-product/goals", body: request, idempotencyKey: idempotencyKey)
    }

    public func updateGoal(id: Int, _ request: GoalRequest, idempotencyKey: String) async throws -> Goal {
        try WriteContract.check(request)
        return try await client.send("PUT", "/user-product/goals/\(id)", body: request, idempotencyKey: idempotencyKey)
    }

    public func deleteGoal(id: Int) async throws {
        let _: Acknowledgement = try await client.send("DELETE", "/user-product/goals/\(id)")
    }

    public func contribute(goalID: Int, _ contribution: GoalContribution, idempotencyKey: String) async throws -> Goal {
        try WriteContract.checkAmount(contribution.amount)
        try WriteContract.checkDate(contribution.contributionDate)
        return try await client.send("POST", "/user-product/goals/\(goalID)/contributions", body: contribution, idempotencyKey: idempotencyKey)
    }

    public func savingsPlans() async throws -> [SavingsPlan] { try await client.get("/user-product/savings-plans") }

    public func createSavingsPlan(_ request: SavingsPlanRequest, idempotencyKey: String) async throws -> SavingsPlan {
        try WriteContract.check(request)
        return try await client.send("POST", "/user-product/savings-plans", body: request, idempotencyKey: idempotencyKey)
    }

    public func deleteSavingsPlan(id: Int) async throws {
        let _: Acknowledgement = try await client.send("DELETE", "/user-product/savings-plans/\(id)")
    }

    public func contribute(savingsPlanID: Int, _ contribution: GoalContribution, idempotencyKey: String) async throws -> SavingsPlan {
        try WriteContract.checkAmount(contribution.amount)
        try WriteContract.checkDate(contribution.contributionDate)
        return try await client.send("POST", "/user-product/savings-plans/\(savingsPlanID)/contributions", body: contribution, idempotencyKey: idempotencyKey)
    }

    // MARK: Financial situation (G2, F10)

    public func financialSituation() async throws -> FinancialSituation { try await client.get("/user-product/financial-situation") }

    /// Full replacement: unknown fields travel as null, never as zero.
    public func updateFinancialSituation(_ profile: FinancialProfile, idempotencyKey: String) async throws -> FinancialSituation {
        try WriteContract.check(profile)
        return try await client.send("PUT", "/user-product/financial-situation", body: profile, idempotencyKey: idempotencyKey)
    }

    // MARK: Basic (C2, E8–E10, F2, reports)

    public func basicDashboard() async throws -> BasicDashboard { try await client.get("/user-product/basic/dashboard") }

    public func budget() async throws -> Budget { try await client.get("/user-product/basic/budget") }

    public func updateBudget(_ update: BudgetUpdate, idempotencyKey: String) async throws -> Budget {
        for item in update.items { try WriteContract.checkAmount(item.monthlyLimit, allowZero: true) }
        return try await client.send("PUT", "/user-product/basic/budget", body: update, idempotencyKey: idempotencyKey)
    }

    public func calendar(period: String) async throws -> FinancialCalendar {
        try await client.get("/user-product/basic/calendar", query: [URLQueryItem(name: "period", value: period)])
    }

    public func recurring() async throws -> RecurringList { try await client.get("/user-product/basic/recurring") }

    public func createRecurring(_ request: RecurringRequest, idempotencyKey: String) async throws -> RecurringList.Item {
        try WriteContract.checkAmount(request.amount)
        return try await client.send("POST", "/user-product/basic/recurring", body: request, idempotencyKey: idempotencyKey)
    }

    public func updateRecurring(id: Int, _ request: RecurringRequest, idempotencyKey: String) async throws -> RecurringList.Item {
        try WriteContract.checkAmount(request.amount)
        return try await client.send("PUT", "/user-product/basic/recurring/\(id)", body: request, idempotencyKey: idempotencyKey)
    }

    public func deleteRecurring(id: Int) async throws {
        let _: Acknowledgement = try await client.send("DELETE", "/user-product/basic/recurring/\(id)")
    }

    public func report(period: String) async throws -> MonthReport {
        try await client.get("/user-product/basic/reports", query: [URLQueryItem(name: "period", value: period)])
    }

    public func strategyBasic() async throws -> Strategy { try await client.get("/user-product/finance/strategy-basic") }

    // MARK: VIP (C3, E11, E12, F3–F9). The Plan tab's strategy dashboards and Salvavidas are in
    // `DincrService+Plan.swift`; the backend picks the Users or Owner model by the server role.

    public func commandCenter() async throws -> CommandCenter { try await client.get("/user-product/vip/command-center") }

    public func strategyVip() async throws -> Strategy { try await client.get("/user-product/finance/strategy-vip") }

    /// A what-if: nothing is saved (the backend route is read-only).
    public func simulate(_ request: ScenarioRequest) async throws -> ScenarioResult {
        try await client.send("POST", "/user-product/finance/strategy-vip/simulate", body: request)
    }

    public func aguinaldo() async throws -> Aguinaldo { try await client.get("/user-product/vip/aguinaldo") }

    public func monthlyReview(period: String) async throws -> MonthlyReview {
        try await client.get("/user-product/vip/lifecycle/monthly-review", query: [URLQueryItem(name: "period", value: period)])
    }

    public func proactiveAdvisor() async throws -> ProactiveAdvisor { try await client.get("/user-product/vip/lifecycle/proactive-advisor") }

    // MARK: Email Monitor (H1–H7; VIP and `gmail_automation`)

    public func mailStatus() async throws -> MailStatus { try await client.get("/user-product/vip/gmail/status") }

    /// Accepts the consent version the backend asked for in `/status` (a stale one is a 409).
    public func acceptMailConsent(version: String) async throws {
        let _: Acknowledgement = try await client.send("POST", "/user-product/vip/gmail/consent", body: MailConsentRequest(version: version))
    }

    /// The provider authorization URL to open in the system authentication session. The backend
    /// builds it (Gmail: `gmail.readonly` only, PKCE, `hl` from `locale`); the app never adds scopes.
    public func connectMail(_ provider: MailReturn.Provider, _ request: MailConnectRequest) async throws -> URL {
        let path = provider == .gmail ? "/user-product/vip/gmail/connect" : "/user-product/vip/mail/microsoft/connect"
        let response: MailConnectResponse = try await client.send("POST", path, body: request)
        guard let url = URL(string: response.authorizationUrl), url.scheme?.lowercased() == "https", url.host != nil else {
            throw APIError(kind: .decoding, message: AppLanguage.current.pick("Recibimos una dirección de conexión inválida.", "We received an invalid connection address."))
        }
        return url
    }

    /// Attaches the mailbox the provider authorized. Only the session that started the flow can.
    public func completeMailConnection(flow: String, completion: String) async throws -> MailCompleteResponse {
        try await client.send("POST", "/user-product/vip/mail/oauth/complete", body: MailCompleteRequest(flow: flow, completion: completion))
    }

    public func syncMail() async throws -> MailSyncResult { try await client.send("POST", "/user-product/vip/gmail/sync") }

    public func disconnectMail(connectionID: Int) async throws {
        let _: Acknowledgement = try await client.send("DELETE", "/user-product/vip/gmail", query: [URLQueryItem(name: "connection_id", value: String(connectionID))])
    }

    /// `pendingOnly` asks for `status=pending`; otherwise every reviewed state too.
    public func mailCandidates(pendingOnly: Bool) async throws -> [MailCandidate] {
        let list: MailCandidateList = try await client.get("/user-product/vip/gmail/emails", query: [URLQueryItem(name: "status", value: pendingOnly ? "pending" : "")])
        return list.items ?? []
    }

    /// Accept as detected. A candidate already reviewed answers `already_reviewed` and writes nothing.
    public func acceptCandidate(id: Int) async throws -> CandidateReviewResult {
        try await client.send("POST", "/user-product/vip/gmail/candidates/\(id)/accept")
    }

    /// Accept with the user's corrections (amount in the notice's own currency, and the user's rate
    /// when that currency is not the account's).
    public func correctCandidate(id: Int, _ correction: CandidateCorrection) async throws -> CandidateReviewResult {
        try WriteContract.checkAmount(correction.amount)
        try WriteContract.checkDate(correction.transactionDate)
        if let rate = correction.exchangeRate { try WriteContract.checkRate(rate) }
        return try await client.send("PUT", "/user-product/vip/gmail/candidates/\(id)/accept", body: correction)
    }

    /// Never creates a transaction.
    public func rejectCandidate(id: Int) async throws -> CandidateReviewResult {
        try await client.send("POST", "/user-product/vip/gmail/candidates/\(id)/reject")
    }

    public func ownTransferSuggestions() async throws -> OwnTransferSuggestions { try await client.get("/user-product/vip/gmail/own-transfer-suggestions") }

    public func confirmOwnTransfer(candidateID: Int, _ request: OwnTransferRequest) async throws {
        let _: Acknowledgement = try await client.send("POST", "/user-product/vip/gmail/candidates/\(candidateID)/own-transfer", body: request)
    }

    public func financialIdentity() async throws -> FinancialIdentity { try await client.get("/user-product/vip/financial-identity") }

    public func setAccountOwnership(id: Int, own: Bool) async throws {
        let _: Acknowledgement = try await client.send("PUT", "/user-product/vip/financial-identity/accounts/\(id)", body: OwnershipRequest(own: own))
    }

    /// Movement ids look like `expense:42`; the colon must survive as a path segment.
    static func encode(_ id: String) -> String {
        id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/"))) ?? id
    }
}

/// Earlier name of the live service; kept so call sites read naturally in tests.
public typealias LiveDincrService = DincrService

/// One key per user submission: a retry of the same body reuses it, a new body gets a new key.
public enum IdempotencyKey {
    public static func new() -> String { "op_" + UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased() }
}

/// The key of one amount submission (payment, contribution): retrying the same amount after a
/// failure reuses the key, so a lost response never records the money twice. `10000` and
/// `10000.00` are the same amount.
public struct AmountSubmission {
    private var last: (amount: Decimal, key: String)?
    private let newKey: () -> String

    public init(newKey: @escaping () -> String = IdempotencyKey.new) { self.newKey = newKey }

    public mutating func key(for amount: Decimal) -> String {
        if let last, last.amount == amount { return last.key }
        let key = newKey()
        last = (amount, key)
        return key
    }
}
