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
    /// D3 — `POST /user-product/finance/income` | `/expenses`
    func create(_ kind: Movement.Kind, _ entry: EntryCreate) async throws
    /// D4, D5 — `PUT /user-product/free/movements/{id}`
    func update(movementID: String, _ update: MovementUpdate) async throws
    /// D6 — `DELETE /user-product/free/movements/{id}`
    func delete(movementID: String) async throws
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

    public func create(_ kind: Movement.Kind, _ entry: EntryCreate) async throws {
        let path = kind == .income ? "/user-product/finance/income" : "/user-product/finance/expenses"
        let _: Acknowledgement = try await client.send("POST", path, body: entry)
    }

    public func update(movementID: String, _ update: MovementUpdate) async throws {
        let _: Acknowledgement = try await client.send("PUT", "/user-product/free/movements/\(Self.encode(movementID))", body: update)
    }

    public func delete(movementID: String) async throws {
        let _: Acknowledgement = try await client.send("DELETE", "/user-product/free/movements/\(Self.encode(movementID))")
    }

    /// Movement ids look like `expense:42`; the colon must survive as a path segment.
    static func encode(_ id: String) -> String {
        id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed.subtracting(CharacterSet(charactersIn: "/"))) ?? id
    }
}
