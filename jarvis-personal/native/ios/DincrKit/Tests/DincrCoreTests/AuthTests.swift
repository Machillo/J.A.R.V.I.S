import Foundation
import Testing
@testable import DincrCore

@Suite struct AuthTests {
    @Test func pkceChallengeMatchesRFC7636TestVector() {
        let pkce = PKCE(verifier: "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")
        #expect(pkce.challenge == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")
    }

    @Test func generatedVerifiersAreUniqueAndURLSafe() {
        let a = PKCE.generate(), b = PKCE.generate()
        #expect(a.verifier != b.verifier)
        #expect(a.verifier.count >= 43)
        #expect(!a.verifier.contains("+") && !a.verifier.contains("/") && !a.verifier.contains("="))
    }

    @Test func authorizeURLCarriesPKCEAndProviderOptions() throws {
        let client = SupabaseAuthClient(projectURL: URL(string: "https://project.example.test")!, anonKey: "anon")
        let pkce = PKCE(verifier: "dBjftJeZ4CVP-mJ92K9XgX3VWNdcbmRz3-GrjqTwZqHhWcm")
        let url = client.authorizeURL(provider: .google, redirectTo: "com.dincr.app://auth/callback", pkce: pkce)
        let items = try #require(URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems)
        let query = Dictionary(uniqueKeysWithValues: items.map { ($0.name, $0.value ?? "") })
        #expect(url.path == "/auth/v1/authorize")
        #expect(query["provider"] == "google")
        #expect(query["code_challenge_method"] == "s256")
        #expect(query["code_challenge"] == pkce.challenge)
        #expect(query["prompt"] == "select_account")
        #expect(query["redirect_to"] == "com.dincr.app://auth/callback")
    }

    @Test func callbackAcceptsOnlyACodeOnTheExpectedScheme() throws {
        let prefix = "com.dincr.app://auth/callback"
        #expect(try SupabaseAuthClient.authorizationCode(from: URL(string: "\(prefix)?code=abc")!, expectedPrefix: prefix) == "abc")
        #expect(throws: AuthError.invalidCallback) {
            try SupabaseAuthClient.authorizationCode(from: URL(string: "evil://auth/callback?code=abc")!, expectedPrefix: prefix)
        }
        #expect(throws: AuthError.invalidCallback) {
            // Tokens in the URL (implicit flow) are never accepted.
            try SupabaseAuthClient.authorizationCode(from: URL(string: "\(prefix)#access_token=x&refresh_token=y")!, expectedPrefix: prefix)
        }
        #expect(throws: AuthError.providerRejected) {
            try SupabaseAuthClient.authorizationCode(from: URL(string: "\(prefix)?error=access_denied")!, expectedPrefix: prefix)
        }
    }

    @Test func expiredSessionRefreshesOnceForConcurrentCallers() async throws {
        let body = #"{"access_token":"fresh","refresh_token":"r2","expires_in":3600,"user":{"id":"u1"}}"#
        let transport = ScriptedTransport([.status(200, body)])
        let auth = SupabaseAuthClient(projectURL: URL(string: "https://project.example.test")!, anonKey: "anon", transport: transport)
        let store = InMemorySessionStore(AuthSession(accessToken: "old", refreshToken: "r1", expiresAt: .now.addingTimeInterval(-10), userID: "u1"))
        let manager = SessionManager(auth: auth, store: store)
        async let first = manager.accessToken(forceRefresh: false)
        async let second = manager.accessToken(forceRefresh: false)
        let tokens = try await [first, second]
        #expect(tokens == ["fresh", "fresh"])
        #expect(transport.requests.count == 1, "one refresh for concurrent callers")
        let request = try #require(transport.requests.first)
        #expect(request.url?.query == "grant_type=refresh_token")
        #expect(request.value(forHTTPHeaderField: "apikey") == "anon")
        #expect(store.load()?.refreshToken == "r2")
    }

    @Test func rejectedRefreshSignsOutAndClearsTheDevice() async {
        let transport = ScriptedTransport([.status(400, #"{"error":"invalid_grant"}"#)])
        let auth = SupabaseAuthClient(projectURL: URL(string: "https://project.example.test")!, anonKey: "anon", transport: transport)
        let store = InMemorySessionStore(AuthSession(accessToken: "old", refreshToken: "r1", expiresAt: .now.addingTimeInterval(-10), userID: "u1"))
        let manager = SessionManager(auth: auth, store: store)
        let flag = SignedOutFlag()
        await manager.setSignedOutHandler { flag.set() }
        await #expect(throws: AuthError.signedOut) { try await manager.accessToken(forceRefresh: false) }
        #expect(store.load() == nil)
        #expect(flag.value)
    }

    @Test func networkFailureDuringRefreshKeepsTheSession() async {
        let transport = ScriptedTransport([.failure(.notConnectedToInternet)])
        let auth = SupabaseAuthClient(projectURL: URL(string: "https://project.example.test")!, anonKey: "anon", transport: transport)
        let store = InMemorySessionStore(AuthSession(accessToken: "old", refreshToken: "r1", expiresAt: .now.addingTimeInterval(-10), userID: "u1"))
        let manager = SessionManager(auth: auth, store: store)
        await #expect(throws: APIError.self) { try await manager.accessToken(forceRefresh: false) }
        #expect(store.load() != nil, "being offline must not sign the user out")
    }
}

final class SignedOutFlag: @unchecked Sendable {
    private let lock = NSLock()
    private var flag = false
    func set() { lock.withLock { flag = true } }
    var value: Bool { lock.withLock { flag } }
}
