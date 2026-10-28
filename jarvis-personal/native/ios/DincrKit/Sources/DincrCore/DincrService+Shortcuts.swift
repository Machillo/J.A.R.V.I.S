import Foundation

// Perfil → Atajos de iPhone (VIP and the Owner; the backend answers 403 to Free and Basic). These are
// the three session routes that link and unlink this iPhone. The token the backend issues is stored
// only in the Keychain (`ShortcutTokenStore`) and never logged or shown.
extension DincrService {
    static let shortcutTokenPath = "/user-product/vip/shortcuts/token"

    /// Whether the account has a shortcut token (on any device). A read: it never issues or revokes one.
    public func shortcutLinkStatus() async throws -> ShortcutLinkStatus { try await client.get(Self.shortcutTokenPath) }

    /// Issues a new token; any previous one stops working. A write: never retried on its own.
    public func issueShortcutToken() async throws -> ShortcutTokenIssued { try await client.send("POST", Self.shortcutTokenPath) }

    /// Revokes the account's token. Idempotent on the backend.
    public func revokeShortcutToken() async throws {
        let _: ShortcutLinkStatus = try await client.send("DELETE", Self.shortcutTokenPath)
    }
}

/// `GET` / `DELETE /user-product/vip/shortcuts/token`.
public struct ShortcutLinkStatus: Decodable, Sendable, Equatable {
    public let linked: Bool
    public let createdAt: String?

    public init(linked: Bool, createdAt: String? = nil) { self.linked = linked; self.createdAt = createdAt }

    enum CodingKeys: String, CodingKey { case linked, createdAt }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        // A missing flag is not a link.
        linked = try container.decodeIfPresent(Bool.self, forKey: .linked) ?? false
        createdAt = try container.decodeIfPresent(String.self, forKey: .createdAt)
    }
}

/// `POST /user-product/vip/shortcuts/token`. Its `description` never prints the token.
public struct ShortcutTokenIssued: Decodable, Sendable, CustomStringConvertible {
    public let token: String
    public let createdAt: String?

    public var description: String { "ShortcutTokenIssued(token: <redacted>)" }
}

/// What the Atajos de iPhone screen shows.
public enum ShortcutLinkState: Sendable, Equatable {
    case notLinked
    /// This iPhone holds the account's token.
    case linked
    /// The account has a token, but not on this iPhone (another device, or a reinstall). Activating
    /// here replaces it.
    case linkedElsewhere
}

/// Links and unlinks this iPhone, keeping the Keychain and the backend consistent.
public struct ShortcutLinking: Sendable {
    let service: DincrService
    let store: ShortcutTokenStore

    public init(service: DincrService, store: ShortcutTokenStore) { self.service = service; self.store = store }

    /// VIP and the Owner (the Owner's plan tier is VIP). Free and Basic see the row locked.
    public static let minimumPlan: PlanTier = .vip
    public static func isAvailable(to profile: Profile?) -> Bool { (profile?.planTier ?? .free) >= minimumPlan }

    /// The state for `accountID`, given the backend's answer and what this iPhone holds. A token of
    /// another account, or one the backend no longer has, is forgotten here.
    public static func reconcile(serverLinked: Bool, local: ShortcutCredential?, accountID: Int) -> (state: ShortcutLinkState, forgetLocal: Bool) {
        let mine = local?.accountID == accountID ? local : nil
        let forget = local != nil && (mine == nil || !serverLinked)
        switch (serverLinked, mine != nil) {
        case (true, true): return (.linked, forget)
        case (true, false): return (.linkedElsewhere, forget)
        default: return (.notLinked, forget)
        }
    }

    /// The state as this iPhone alone knows it (before or without the backend's answer).
    public func localState(accountID: Int) -> ShortcutLinkState {
        store.read()?.accountID == accountID ? .linked : .notLinked
    }

    public func status(accountID: Int) async throws -> ShortcutLinkState {
        let answer = try await service.shortcutLinkStatus()
        let (state, forget) = Self.reconcile(serverLinked: answer.linked, local: store.read(), accountID: accountID)
        if forget { store.clear() }
        return state
    }

    /// Issues a token and keeps it in the Keychain. A malformed answer is never stored.
    public func activate(accountID: Int) async throws -> ShortcutLinkState {
        let issued = try await service.issueShortcutToken()
        guard ShortcutCredential.isValidToken(issued.token) else { throw APIError.decoding(.current) }
        store.save(ShortcutCredential(token: issued.token, accountID: accountID))
        return .linked
    }

    /// Revokes the token on the backend, then forgets it here. If the backend cannot be reached the
    /// token stays, so the user can retry (sign-out uses `forget`, which always clears).
    public func deactivate() async throws -> ShortcutLinkState {
        try await service.revokeShortcutToken()
        store.clear()
        return .notLinked
    }

    /// Sign-out, account switch and deletion: a best-effort revoke (only when this iPhone holds a token,
    /// bounded by `timeout`, failures ignored), then the Keychain is ALWAYS cleared.
    public func forget(timeout: Duration = .seconds(4)) async {
        if store.isLinked {
            let service = self.service
            await withTaskGroup(of: Void.self) { group in
                group.addTask { try? await service.revokeShortcutToken() }
                group.addTask { try? await Task.sleep(for: timeout) }
                await group.next()
                group.cancelAll()
            }
        }
        store.clear()
    }
}
