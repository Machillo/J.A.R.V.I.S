import Foundation

// MARK: Personal appearance (APP-1: the Owner only; the backend refuses everyone else)

public extension DincrService {
    func appearance() async throws -> AppearanceState { try await client.get("/user-product/appearance") }

    func saveAppearance(_ preferences: AppearancePreferences) async throws -> AppearanceState {
        try await client.send("PUT", "/user-product/appearance", body: preferences.sanitized())
    }

    /// Back to the defaults: the stored choice is removed on the server.
    func resetAppearance() async throws -> AppearanceState { try await client.send("DELETE", "/user-product/appearance") }
}
