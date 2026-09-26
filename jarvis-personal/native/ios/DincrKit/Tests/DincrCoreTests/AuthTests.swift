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
        let url = client.authorizeURL(provider: .google, redirectTo: Self.redirect, pkce: pkce)
        let items = try #require(URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems)
        let query = Dictionary(uniqueKeysWithValues: items.map { ($0.name, $0.value ?? "") })
        #expect(url.path == "/auth/v1/authorize")
        #expect(query["provider"] == "google")
        #expect(query["code_challenge_method"] == "s256")
        #expect(query["code_challenge"] == pkce.challenge)
        #expect(query["prompt"] == "select_account")
        #expect(query["redirect_to"] == Self.redirect)
    }

    static let redirect = "com.dincr.app.nativedev://auth/callback"

    @Test func callbackAcceptsOnlyACodeOnTheExactRedirect() throws {
        #expect(try SupabaseAuthClient.authorizationCode(from: URL(string: "\(Self.redirect)?code=abc")!, redirect: Self.redirect) == "abc")
        #expect(try SupabaseAuthClient.authorizationCode(from: URL(string: "COM.DINCR.APP.NATIVEDEV://auth/callback?code=abc&state=s")!, redirect: Self.redirect) == "abc")
        #expect(throws: AuthError.providerRejected) {
            try SupabaseAuthClient.authorizationCode(from: URL(string: "\(Self.redirect)?error=access_denied")!, redirect: Self.redirect)
        }
    }

    @Test(arguments: [
        "evil://auth/callback?code=abc",                              // other scheme
        "com.dincr.app://auth/callback?code=abc",                    // the production app's scheme
        "com.dincr.app.nativedev://auth/callbackX?code=abc",         // look-alike path
        "com.dincr.app.nativedev://auth/callback/x?code=abc",
        "com.dincr.app.nativedev://evil/callback?code=abc",          // other host
        "com.dincr.app.nativedev://user@auth/callback?code=abc",
        "com.dincr.app.nativedev://auth:99/callback?code=abc",
        "com.dincr.app.nativedev://auth/callback#access_token=x&refresh_token=y", // implicit-flow tokens
        "com.dincr.app.nativedev://auth/callback?code=abc#access_token=x",
        "com.dincr.app.nativedev://auth/callback",                    // missing code
        "com.dincr.app.nativedev://auth/callback?code=",              // empty code
        "com.dincr.app.nativedev://auth/callback?code=a&code=b",      // ambiguous code
    ])
    func callbackRejectsAnythingElse(url: String) {
        #expect(throws: AuthError.invalidCallback) {
            try SupabaseAuthClient.authorizationCode(from: URL(string: url)!, redirect: Self.redirect)
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
