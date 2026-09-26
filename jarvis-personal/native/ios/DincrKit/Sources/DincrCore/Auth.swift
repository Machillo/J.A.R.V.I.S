import CryptoKit
import Foundation
import Security

/// A Supabase Auth session as returned by GoTrue.
public struct AuthSession: Codable, Sendable, Equatable {
    public let accessToken: String
    public let refreshToken: String
    public let expiresAt: Date
    public let userID: String

    public init(accessToken: String, refreshToken: String, expiresAt: Date, userID: String) {
        self.accessToken = accessToken; self.refreshToken = refreshToken; self.expiresAt = expiresAt; self.userID = userID
    }

    /// Refresh a minute early so a request never leaves with an expiring token.
    public func isExpired(now: Date = .now) -> Bool { now.addingTimeInterval(60) >= expiresAt }
}

public enum OAuthProvider: String, Sendable { case google, apple }

/// PKCE pair. Only the verifier's hash leaves the device; the verifier stays in memory until
/// the code exchange, so a crafted deep link cannot inject someone else's session
/// (same rule as `frontend/src/lib/nativeAuth.js`: only `code` is accepted, never tokens).
public struct PKCE: Sendable, Equatable {
    public let verifier: String
    public let challenge: String

    public init(verifier: String) {
        self.verifier = verifier
        let digest = SHA256.hash(data: Data(verifier.utf8))
        self.challenge = Data(digest).base64URLEncoded
    }

    public static func generate() -> PKCE {
        var bytes = [UInt8](repeating: 0, count: 32)
        _ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        return PKCE(verifier: Data(bytes).base64URLEncoded)
    }
}

/// Minimal GoTrue client for the three calls the app needs.
public struct SupabaseAuthClient: Sendable {
    public let projectURL: URL
    let anonKey: String
    let transport: HTTPTransport

    public init(projectURL: URL, anonKey: String, transport: HTTPTransport = URLSessionTransport()) {
        self.projectURL = projectURL; self.anonKey = anonKey; self.transport = transport
    }

    public func authorizeURL(provider: OAuthProvider, redirectTo: String, pkce: PKCE) -> URL {
        var components = URLComponents(url: projectURL.appending(path: "/auth/v1/authorize"), resolvingAgainstBaseURL: false)!
        var items = [
            URLQueryItem(name: "provider", value: provider.rawValue),
            URLQueryItem(name: "redirect_to", value: redirectTo),
            URLQueryItem(name: "code_challenge", value: pkce.challenge),
            URLQueryItem(name: "code_challenge_method", value: "s256"),
        ]
        switch provider {
        case .google: items.append(URLQueryItem(name: "prompt", value: "select_account"))
        case .apple: items.append(URLQueryItem(name: "scopes", value: "name email"))
        }
        components.queryItems = items
        return components.url!
    }

    /// Extracts the authorization code from the callback. Errors reported by the provider and
    /// callbacks without a code are rejected.
    public static func authorizationCode(from callback: URL, expectedPrefix: String) throws -> String {
        guard callback.absoluteString.hasPrefix(expectedPrefix),
              let items = URLComponents(url: callback, resolvingAgainstBaseURL: false)?.queryItems else {
            throw AuthError.invalidCallback
        }
        if items.contains(where: { $0.name == "error" || $0.name == "error_description" }) { throw AuthError.providerRejected }
        guard let code = items.first(where: { $0.name == "code" })?.value, !code.isEmpty else { throw AuthError.invalidCallback }
        return code
    }

    public func exchange(code: String, verifier: String) async throws -> AuthSession {
        try await token(grant: "pkce", body: ["auth_code": code, "code_verifier": verifier])
    }

    public func refresh(_ refreshToken: String) async throws -> AuthSession {
        try await token(grant: "refresh_token", body: ["refresh_token": refreshToken])
    }

    public func signOut(accessToken: String) async {
        var request = URLRequest(url: projectURL.appending(path: "/auth/v1/logout").appending(queryItems: [URLQueryItem(name: "scope", value: "local")]))
        request.httpMethod = "POST"
        request.setValue(anonKey, forHTTPHeaderField: "apikey")
        request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        _ = try? await transport.send(request)
    }

    private func token(grant: String, body: [String: String]) async throws -> AuthSession {
        var request = URLRequest(url: projectURL.appending(path: "/auth/v1/token").appending(queryItems: [URLQueryItem(name: "grant_type", value: grant)]), timeoutInterval: 20)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(anonKey, forHTTPHeaderField: "apikey")
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let data: Data
        let response: HTTPURLResponse
        do { (data, response) = try await transport.send(request) } catch { throw AuthError.network }
        guard (200..<300).contains(response.statusCode) else {
            throw response.statusCode >= 500 ? AuthError.network : AuthError.sessionRejected
        }
        struct Payload: Decodable {
            struct User: Decodable { let id: String }
            let access_token: String
            let refresh_token: String
            let expires_in: Double?
            let expires_at: Double?
            let user: User
        }
        guard let payload = try? JSONDecoder().decode(Payload.self, from: data) else { throw AuthError.sessionRejected }
        let expiry = payload.expires_at.map { Date(timeIntervalSince1970: $0) }
            ?? Date().addingTimeInterval(payload.expires_in ?? 3600)
        return AuthSession(accessToken: payload.access_token, refreshToken: payload.refresh_token, expiresAt: expiry, userID: payload.user.id)
    }
}

public enum AuthError: Error, Sendable, Equatable {
    case invalidCallback, providerRejected, sessionRejected, network, signedOut, cancelled
}

/// Where the session lives between launches.
public protocol SessionStore: Sendable {
    func load() -> AuthSession?
    func save(_ session: AuthSession)
    func clear()
}

/// Keychain storage, readable only while the device is unlocked, never synced or backed up
/// to another device.
public struct KeychainSessionStore: SessionStore {
    let service: String
    let account = "supabase-session"

    public init(service: String = "com.dincr.app.session") { self.service = service }

    private var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: account]
    }

    public func load() -> AuthSession? {
        var request = query
        request[kSecReturnData as String] = true
        request[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(request as CFDictionary, &item) == errSecSuccess, let data = item as? Data else { return nil }
        return try? JSONDecoder().decode(AuthSession.self, from: data)
    }

    public func save(_ session: AuthSession) {
        guard let data = try? JSONEncoder().encode(session) else { return }
        SecItemDelete(query as CFDictionary)
        var item = query
        item[kSecValueData as String] = data
        item[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        SecItemAdd(item as CFDictionary, nil)
    }

    public func clear() { SecItemDelete(query as CFDictionary) }
}

public final class InMemorySessionStore: SessionStore, @unchecked Sendable {
    private let lock = NSLock()
    private var session: AuthSession?
    public init(_ session: AuthSession? = nil) { self.session = session }
    public func load() -> AuthSession? { lock.withLock { session } }
    public func save(_ session: AuthSession) { lock.withLock { self.session = session } }
    public func clear() { lock.withLock { session = nil } }
}

/// Owns the current session: restores it, refreshes it once at a time, and reports sign-out.
/// It is the API client's token provider.
public actor SessionManager: AccessTokenProvider {
    let auth: SupabaseAuthClient?
    let store: SessionStore
    private var refreshing: Task<AuthSession, Error>?
    private var onSignedOut: (@Sendable () -> Void)?

    public init(auth: SupabaseAuthClient?, store: SessionStore) {
        self.auth = auth; self.store = store
    }

    public func setSignedOutHandler(_ handler: @escaping @Sendable () -> Void) { onSignedOut = handler }

    public var hasSession: Bool { store.load() != nil }

    public func accept(_ session: AuthSession) { store.save(session) }

    public func accessToken(forceRefresh: Bool) async throws -> String {
        guard let session = store.load() else { throw AuthError.signedOut }
        if !forceRefresh, !session.isExpired() { return session.accessToken }
        return try await refreshed(from: session).accessToken
    }

    public func signOut() async {
        if let session = store.load() { await auth?.signOut(accessToken: session.accessToken) }
        store.clear()
    }

    private func refreshed(from session: AuthSession) async throws -> AuthSession {
        if let refreshing { return try await refreshing.value }
        guard let auth else { return session }
        let task = Task { try await auth.refresh(session.refreshToken) }
        refreshing = task
        defer { refreshing = nil }
        do {
            let fresh = try await task.value
            store.save(fresh)
            return fresh
        } catch AuthError.network {
            throw APIError.offline(.current)
        } catch {
            // The refresh token is no longer valid: the session is over on this device.
            store.clear()
            onSignedOut?()
            throw AuthError.signedOut
        }
    }
}

extension Data {
    var base64URLEncoded: String {
        base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
    }
}
