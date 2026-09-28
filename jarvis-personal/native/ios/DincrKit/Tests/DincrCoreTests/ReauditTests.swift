import Foundation
import Testing
@testable import DincrCore

/// Re-audit of C4 against main after #269/#272 (money limits, currency rows, launch policy,
/// session isolation, redirects). The Kotlin twin is `ReauditTest` in android/core/data.
@Suite struct ReauditTests {
    // MARK: Money limits — amount is NUMERIC(12,2) for every write of this app

    @Test func amountLimitIsTheColumnOfEveryWrite() {
        let max = Decimal(string: "9999999999.99")!
        #expect(AmountInput.maxAmount == max)
        #expect(AmountInput.parse("9.999.999.999,99", separators: .dotComma) == max)
        #expect(AmountInput.parse("9999999999,99", separators: .dotComma) == max)
        #expect(AmountInput.parse("9,999,999,999.99", separators: .commaDot) == max)
        #expect(AmountInput.parse("0,01", separators: .dotComma) == Decimal(string: "0.01"))
        let rejected: [(String, MoneyFormat.Separators)] = [
            ("10.000.000.000", .dotComma), ("10.000.000.000,00", .dotComma), ("10000000000", .dotComma),
            ("99.999.999.999,99", .dotComma), ("10,000,000,000.00", .commaDot), ("999999999999.99", .commaDot),
            ("1e30", .dotComma), ("1e300", .commaDot), ("1E+30", .commaDot), ("NaN", .dotComma), ("Infinity", .commaDot),
            ("-Infinity", .dotComma), ("-0,01", .dotComma), ("0", .dotComma), ("0,00", .dotComma), ("0x10", .commaDot),
            ("9.999.999.999,991", .dotComma), ("1,000", .dotComma), ("1.000", .commaDot), ("1.5", .dotComma),
            ("１２", .dotComma), ("٣", .dotComma),
        ]
        for (text, separators) in rejected {
            #expect(AmountInput.parse(text, separators: separators) == nil, "\(text) must be rejected")
        }
    }

    @Test func displayRoundsHalfUpButEditingKeepsCents() {
        let crc = MoneyFormat(currency: "CRC", separators: .dotComma)
        #expect(crc.string(Decimal(string: "2.5")!) == "₡3")
        #expect(crc.inputText(Decimal(string: "18450.50")!) == "18.450,5")
        #expect(AmountInput.parse(crc.inputText(Decimal(string: "18450.50")!), separators: .dotComma) == Decimal(string: "18450.5"))
        #expect(crc.inputText(Decimal(string: "9999999999.99")!) == "9.999.999.999,99")
    }

    // MARK: Untouched edits send the stored amount digit for digit, and never a currency

    private func sentAmount(_ body: Data) -> Decimal? {
        let text = String(decoding: body, as: UTF8.self)
        guard let range = text.range(of: "\"amount\":") else { return nil }
        let raw = text[range.upperBound...].prefix { "0123456789.-+eE".contains($0) }
        return Decimal(string: String(raw), locale: Locale(identifier: "en_US_POSIX"))
    }

    @Test(arguments: ["9999999999.99", "0.1", "0.01", "18450.5", "100.10", "1234567.89"])
    func untouchedAmountRoundTripsExactly(stored: String) throws {
        let json = #"{"movement_id":"expense:1","transaction_date":"2026-09-01","amount":\#(stored),"transaction_type":"expense","editable":true}"#
        let row = try APIClient.decoder.decode(Movement.self, from: Data(json.utf8))
        let body = try APIClient.encoder.encode(MovementUpdate(transactionDate: "2026-09-01", description: "x", amount: row.amount, transactionType: .expense, category: "Otros"))
        #expect(sentAmount(body) == Decimal(string: stored, locale: Locale(identifier: "en_US_POSIX")), "\(stored)")
    }

    @Test func writesNeverCarryACurrencyOrRate() throws {
        let update = try APIClient.encoder.encode(MovementUpdate(transactionDate: "2026-09-01", description: "x", amount: 1, transactionType: .expense, category: "Otros"))
        let create = try APIClient.encoder.encode(EntryCreate(amount: 1, description: "x", category: "Otros", entryDate: "2026-09-01"))
        for body in [update, create] {
            let keys = Set((try JSONSerialization.jsonObject(with: body) as? [String: Any] ?? [:]).keys)
            #expect(keys.isDisjoint(with: ["currency", "exchange_rate", "original_amount", "original_currency"]), "\(keys)")
        }
    }

    // MARK: Rows whose PUT would erase original_* stay read-only

    private func row(_ extra: String, date: String = #""2026-09-01""#) throws -> Movement {
        let json = #"{"movement_id":"expense:1","transaction_date":\#(date),"amount":5200,"transaction_type":"expense","editable":true\#(extra)}"#
        return try APIClient.decoder.decode(Movement.self, from: Data(json.utf8))
    }

    @Test func rowsWithCurrencyDataOrNoDateAreReadOnly() throws {
        #expect(try row("").isEditable)
        #expect(try row("", date: #""2026-09-01T12:00:00""#).isEditable)
        #expect(try row(#","original_amount":10,"original_currency":"USD","exchange_rate":520"#).isEditable == false, "another currency")
        #expect(try row(#","original_amount":5200,"original_currency":"CRC""#).isEditable == false, "currency equal to the base")
        #expect(try row(#","exchange_rate":520"#).isEditable == false, "only the rate")
        #expect(try row(#","original_amount":10"#).isEditable == false, "only the typed amount")
        #expect(try row(#","original_currency":"usd""#).isEditable == false, "only the currency")
        #expect(try row(#","original_currency":"CRC""#).isEditable == false, "only the base currency")
        #expect(try row("", date: "null").isEditable == false, "no date")
        #expect(try row("", date: #""septiembre""#).isEditable == false, "unusable date")
        let locked = #"{"movement_id":"expense:1","transaction_date":"2026-09-01","amount":1,"transaction_type":"expense","editable":false}"#
        #expect(try APIClient.decoder.decode(Movement.self, from: Data(locked.utf8)).isEditable == false, "backend says no")
        #expect(try row(#","exchange_rate":520"#).exchangeRate == 520)
    }

    // MARK: Launch policy — never silent fixtures, never fixtures in Release, HTTPS only

    static let https = "https://api.example.test"
    static let supabase = "https://project.example.test"

    @Test func releaseNeverRunsOnFixtures() {
        for launch in ["populated", "empty", ""] {
            let decision = LaunchPolicy.decide(debugBuild: false, launchFixtures: launch, apiURL: Self.https, supabaseURL: Self.supabase, anonKey: "anon")
            if case .live = decision {} else { Issue.record("\(launch) → \(decision)") }
            #expect(LaunchPolicy.decide(debugBuild: false, launchFixtures: launch, apiURL: "", supabaseURL: "", anonKey: "") == .unconfigured(.missing))
        }
    }

    @Test func missingConfigurationNeverFallsBackToFixtures() {
        let cases: [(String?, String?, String?)] = [("", Self.supabase, "anon"), (Self.https, " ", "anon"), (Self.https, Self.supabase, ""),
                                                   (nil, nil, nil), ("$(DINCR_API_URL)", Self.supabase, "anon")]
        for debug in [true, false] {
            for (api, url, key) in cases {
                #expect(LaunchPolicy.decide(debugBuild: debug, launchFixtures: nil, apiURL: api, supabaseURL: url, anonKey: key) == .unconfigured(.missing))
            }
        }
    }

    @Test func debugFixturesOnlyWhenAskedFor() {
        #expect(LaunchPolicy.decide(debugBuild: true, launchFixtures: "empty", apiURL: "", supabaseURL: "", anonKey: "") == .fixtures(scenario: "empty"))
        #expect(LaunchPolicy.decide(debugBuild: true, launchFixtures: "", apiURL: "", supabaseURL: "", anonKey: "") == .fixtures(scenario: nil))
        let live = LaunchPolicy.decide(debugBuild: true, launchFixtures: nil, apiURL: Self.https, supabaseURL: Self.supabase, anonKey: "anon")
        #expect(live == .live(apiURL: URL(string: Self.https)!, supabaseURL: URL(string: Self.supabase)!, anonKey: "anon"))
    }

    @Test func backendMustBeHttps() {
        func decide(_ debug: Bool, _ api: String, _ supabase: String = Self.supabase) -> LaunchPolicy.Decision {
            LaunchPolicy.decide(debugBuild: debug, launchFixtures: nil, apiURL: api, supabaseURL: supabase, anonKey: "anon")
        }
        #expect(decide(false, "http://api.example.test") == .unconfigured(.insecureURL))
        #expect(decide(false, Self.https, "http://project.example.test") == .unconfigured(.insecureURL))
        #expect(decide(false, "http://localhost:8000") == .unconfigured(.insecureURL))
        #expect(decide(true, "http://api.example.test") == .unconfigured(.insecureURL))
        #expect(decide(true, "ftp://api.example.test") == .unconfigured(.insecureURL))
        if case .live = decide(true, "http://localhost:8000", "http://127.0.0.1:54321") {} else { Issue.record("loopback HTTP is allowed in Debug") }
        #expect(decide(false, "https://user:pw@api.example.test") == .unconfigured(.invalidURL))
        #expect(decide(false, "https:///nohost") == .unconfigured(.invalidURL))
        #expect(decide(false, "not a url") == .unconfigured(.invalidURL))
        #expect(decide(false, "https://api.example.test/?next=http://x") == .unconfigured(.invalidURL))
    }

    // MARK: Session isolation — a refresh never lands on another session

    static let expiredA = AuthSession(accessToken: "a-old", refreshToken: "ra", expiresAt: .now.addingTimeInterval(-10), userID: "user-a")
    static let liveB = AuthSession(accessToken: "b-live", refreshToken: "rb", expiresAt: .now.addingTimeInterval(3600), userID: "user-b")

    private func makeManager(_ transport: HeldTransport, _ store: InMemorySessionStore, _ flag: SignedOutFlag = SignedOutFlag()) async -> SessionManager {
        let auth = SupabaseAuthClient(projectURL: URL(string: "https://project.example.test")!, anonKey: "anon", transport: transport)
        let manager = SessionManager(auth: auth, store: store)
        await manager.setSignedOutHandler { flag.set() }
        return manager
    }

    @Test func signOutDuringRefreshStaysSignedOut() async throws {
        let transport = HeldTransport(holding: "ra")
        let store = InMemorySessionStore(Self.expiredA)
        let flag = SignedOutFlag()
        let manager = await makeManager(transport, store, flag)
        let request = Task { try await manager.accessToken(forceRefresh: false) }
        await transport.started.wait()
        store.clear() // what signOut() does first; the network logout is best effort
        await transport.gate.open()
        await #expect(throws: AuthError.sessionChanged) { try await request.value }
        #expect(store.load() == nil, "the old session's refresh must not sign it back in")
        #expect(flag.value == false)
    }

    @Test func anotherSignInDuringRefreshKeepsTheNewSession() async throws {
        let transport = HeldTransport(holding: "ra")
        let store = InMemorySessionStore(Self.expiredA)
        let manager = await makeManager(transport, store)
        let requestA = Task { try await manager.accessToken(forceRefresh: false) }
        await transport.started.wait()
        await manager.accept(Self.liveB)
        #expect(try await manager.accessToken(forceRefresh: false) == "b-live")
        await transport.gate.open()
        await #expect(throws: AuthError.sessionChanged) { try await requestA.value }
        #expect(store.load() == Self.liveB)
    }

    @Test func anotherSessionNeverAwaitsTheOldRefresh() async throws {
        let transport = HeldTransport(holding: "ra")
        let store = InMemorySessionStore(Self.expiredA)
        let manager = await makeManager(transport, store)
        let requestA = Task { try await manager.accessToken(forceRefresh: false) }
        await transport.started.wait()
        await manager.accept(AuthSession(accessToken: "b-old", refreshToken: "rb", expiresAt: .now.addingTimeInterval(-10), userID: "user-b"))
        // B's own expired session refreshes on its own; it never waits for, or receives, A's.
        #expect(try await manager.accessToken(forceRefresh: false) == "rb-access")
        await transport.gate.open()
        await #expect(throws: AuthError.sessionChanged) { try await requestA.value }
        #expect(store.load()?.refreshToken == "rb-next")
    }

    @Test func rejectedRefreshOfAnOldSessionDoesNotSignOutTheNewOne() async throws {
        let transport = HeldTransport(holding: "ra", status: 400)
        let store = InMemorySessionStore(Self.expiredA)
        let flag = SignedOutFlag()
        let manager = await makeManager(transport, store, flag)
        let requestA = Task { try await manager.accessToken(forceRefresh: false) }
        await transport.started.wait()
        await manager.accept(Self.liveB)
        await transport.gate.open()
        await #expect(throws: AuthError.sessionChanged) { try await requestA.value }
        #expect(store.load() == Self.liveB)
        #expect(flag.value == false)
    }

    @Test func cancelledCallerDoesNotSignOut() async throws {
        let transport = HeldTransport(holding: "ra")
        let store = InMemorySessionStore(Self.expiredA)
        let flag = SignedOutFlag()
        let manager = await makeManager(transport, store, flag)
        let request = Task { try await manager.accessToken(forceRefresh: false) }
        await transport.started.wait()
        request.cancel()
        await transport.gate.open()
        _ = await request.result
        #expect(store.load()?.refreshToken == "ra-next", "the refresh finishes for the session that asked")
        #expect(flag.value == false)
    }

    @Test func signOutClearsBeforeTheNetworkCall() async throws {
        let transport = HeldTransport(holding: nil, status: 204)
        let store = InMemorySessionStore(Self.liveB)
        let manager = await makeManager(transport, store)
        let signOut = Task { await manager.signOut() }
        await transport.started.wait()
        #expect(store.load() == nil, "no request may use the session while Supabase is told")
        await #expect(throws: AuthError.signedOut) { try await manager.accessToken(forceRefresh: false) }
        await transport.gate.open()
        await signOut.value
    }

    // MARK: Network — no redirects, so a bearer token is never replayed elsewhere

    @Test func transportRefusesRedirects() async {
        let original = URL(string: "https://api.example.test/auth/me")!
        let elsewhere = URLRequest(url: URL(string: "https://elsewhere.example.test/")!)
        let redirect = HTTPURLResponse(url: original, statusCode: 302, httpVersion: nil, headerFields: ["Location": "https://elsewhere.example.test/"])!
        let task = URLSession.shared.dataTask(with: original)
        let next = await RefuseRedirects.shared.urlSession(.shared, task: task, willPerformHTTPRedirection: redirect, newRequest: elsewhere)
        #expect(next == nil)
    }
}

/// A one-shot signal that tasks can wait for.
actor Gate {
    private var isOpen = false
    private var waiters: [CheckedContinuation<Void, Never>] = []

    func wait() async {
        if isOpen { return }
        await withCheckedContinuation { waiters.append($0) }
    }

    func open() {
        isOpen = true
        waiters.forEach { $0.resume() }
        waiters.removeAll()
    }
}

/// Holds the requests that carry `holding` as refresh token (every request when nil) until
/// `gate` opens; answers the others at once. A 200 echoes `<refresh>-access` / `<refresh>-next`.
final class HeldTransport: HTTPTransport, @unchecked Sendable {
    let started = Gate()
    let gate = Gate()
    private let holding: String?
    private let status: Int

    init(holding: String?, status: Int = 200) {
        self.holding = holding
        self.status = status
    }

    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) {
        let body = request.httpBody.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: String] }
        let refresh = body?["refresh_token"] ?? ""
        if holding == nil || refresh == holding {
            await started.open()
            await gate.wait()
        }
        let text = status == 200
            ? #"{"access_token":"\#(refresh)-access","refresh_token":"\#(refresh)-next","expires_in":3600,"user":{"id":"u"}}"#
            : "{}"
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!
        return (Data(text.utf8), response)
    }
}
