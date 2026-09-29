import Foundation

/// The backend operations the native app uses. Each maps 1:1 to a FastAPI route consumed by the
/// Capacitor app (parity IDs in docs/native/PARITY_MATRIX.md).
public protocol DincrService: Sendable {
    /// A5, A14 — `GET /auth/me`
    func me() async throws -> Profile
    /// A9 — `POST /auth/profile-setup`
    func completeProfileSetup(_ setup: ProfileSetup) async throws -> Profile
    /// C1 — `GET /user-product/free/dashboard`
    func freeDashboard() async throws -> FreeDashboard
    /// D1, D5 — `GET /user-product/free/movements`
    func movements() async throws -> [Movement]
    /// D3 — `POST /user-product/finance/income` | `/expenses`. `idempotencyKey` identifies one
    /// user submission (8–80 of `A-Za-z0-9_-`): sending it again cannot create a second row.
    func create(_ kind: Movement.Kind, _ entry: EntryCreate, idempotencyKey: String) async throws
    /// D4, D5 — `PUT /user-product/free/movements/{id}`
    func update(movementID: String, _ update: MovementUpdate) async throws
    /// D6 — `DELETE /user-product/free/movements/{id}`
    func delete(movementID: String) async throws

    /// A8 — `POST /auth/legal/accept` with the versions `/auth/me` asked for.
    func acceptLegal(_ request: LegalAcceptRequest) async throws -> LegalAcceptResult
    /// A11 — `GET /auth/plans`
    func plans() async throws -> [PlanOption]
    /// A11 — `GET /product-ops/billing/catalog` (prices and the launch promotion)
    func billingCatalog() async throws -> BillingCatalog
    /// A11, G3 — `POST /auth/plan`
    func choosePlan(_ request: PlanChangeRequest) async throws -> PlanChangeResult
    /// B5 — `GET /product-ops/feature-flags`
    func featureFlags() async throws -> FeatureFlags
    /// G8 — `DELETE /auth/me` (the backend schedules the deletion and closes the account)
    func deleteAccount() async throws
    /// E1 — `GET /user-product/finance/debts`
    func debts() async throws -> [Debt]
    /// E3 — `POST /user-product/finance/debts/{id}/payments`
    func payDebt(id: Int, amount: Decimal, idempotencyKey: String) async throws -> DebtPaymentResult
    /// E5 — `GET /user-product/goals`
    func goals() async throws -> [Goal]
    /// E7 — `POST /user-product/goals/{id}/contributions`
    func contribute(goalID: Int, _ contribution: GoalContribution, idempotencyKey: String) async throws -> Goal
}

public struct LiveDincrService: DincrService {
    let client: APIClient

    public init(client: APIClient) { self.client = client }

    public func me() async throws -> Profile { try await client.get("/auth/me") }

    public func completeProfileSetup(_ setup: ProfileSetup) async throws -> Profile {
        let envelope: ProfileEnvelope = try await client.send("POST", "/auth/profile-setup", body: setup)
        return envelope.profile
    }

    public func freeDashboard() async throws -> FreeDashboard { try await client.get("/user-product/free/dashboard") }

    public func movements() async throws -> [Movement] { try await client.get("/user-product/free/movements") }

    public func create(_ kind: Movement.Kind, _ entry: EntryCreate, idempotencyKey: String) async throws {
        let path = kind == .income ? "/user-product/finance/income" : "/user-product/finance/expenses"
        let _: Acknowledgement = try await client.send("POST", path, body: entry, idempotencyKey: idempotencyKey)
    }

    public func update(movementID: String, _ update: MovementUpdate) async throws {
        let _: Acknowledgement = try await client.send("PUT", "/user-product/free/movements/\(Self.encode(movementID))", body: update)
    }

    public func delete(movementID: String) async throws {
        let _: Acknowledgement = try await client.send("DELETE", "/user-product/free/movements/\(Self.encode(movementID))")
    }

    public func acceptLegal(_ request: LegalAcceptRequest) async throws -> LegalAcceptResult {
        try await client.send("POST", "/auth/legal/accept", body: request)
    }

    public func plans() async throws -> [PlanOption] { try await client.get("/auth/plans") }

    public func billingCatalog() async throws -> BillingCatalog { try await client.get("/product-ops/billing/catalog") }

    public func choosePlan(_ request: PlanChangeRequest) async throws -> PlanChangeResult {
        try await client.send("POST", "/auth/plan", body: request)
    }

    public func featureFlags() async throws -> FeatureFlags { try await client.get("/product-ops/feature-flags") }

    public func deleteAccount() async throws {
        let _: Acknowledgement = try await client.send("DELETE", "/auth/me")
    }

    public func debts() async throws -> [Debt] { try await client.get("/user-product/finance/debts") }

    public func payDebt(id: Int, amount: Decimal, idempotencyKey: String) async throws -> DebtPaymentResult {
        try WriteContract.checkAmount(amount)
        return try await client.send("POST", "/user-product/finance/debts/\(id)/payments", body: AmountRequest(amount: amount), idempotencyKey: idempotencyKey)
    }

    public func goals() async throws -> [Goal] { try await client.get("/user-product/goals") }

    public func contribute(goalID: Int, _ contribution: GoalContribution, idempotencyKey: String) async throws -> Goal {
        try WriteContract.checkAmount(contribution.amount)
        try WriteContract.checkDate(contribution.contributionDate)
        return try await client.send("POST", "/user-product/goals/\(goalID)/contributions", body: contribution, idempotencyKey: idempotencyKey)
    }

    /// Movement ids look like `expense:42`; the colon must survive as a path segment.
    static func encode(_ id: String) -> String {
        id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/"))) ?? id
    }
}
