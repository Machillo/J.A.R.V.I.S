import Foundation
import Testing
@testable import DincrCore

/// Email Monitor contract and invariants for the native iOS port. Shapes are the backend's
/// (`user_product/gmail_service.py`, `mail_oauth.py`, `models.py`), not the Android fake's.
@Suite struct EmailMonitorTests {
    func client(_ transport: ScriptedTransport) -> APIClient {
        APIClient(baseURL: URL(string: "https://api.example.test")!, tokens: CountingTokens(), transport: transport, language: .spanish, backoff: { _ in })
    }

    static func body(_ request: URLRequest) throws -> [String: Any] {
        try #require(JSONSerialization.jsonObject(with: request.httpBody ?? Data()) as? [String: Any])
    }

    // MARK: Scope — gmail.readonly, exactly, and only on the server

    /// The backend builds the Google URL; its single scope constant must stay read-only. This reads the
    /// backend source in the same repository, so widening the scope fails here too.
    @Test func backendAsksGoogleOnlyForGmailReadonly() throws {
        let file = IdentityGuardTests.iosRoot.deletingLastPathComponent().deletingLastPathComponent().appending(path: "backend/user_product/gmail_service.py")
        let source = try String(contentsOf: file, encoding: .utf8)
        #expect(source.contains(#"GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly""#))
        let scopes = source.components(separatedBy: "https://www.googleapis.com/auth/").dropFirst().map { $0.prefix { $0.isLetter || $0 == "." || $0 == "_" } }
        #expect(!scopes.isEmpty)
        #expect(scopes.allSatisfy { $0 == "gmail.readonly" }, "only gmail.readonly may appear: \(scopes)")
        #expect(!source.contains("gmail.modify") && !source.contains("gmail.metadata") && !source.contains("https://mail.google.com"))
        #expect(!source.contains("include_granted_scopes\","), "incremental scopes would widen the token")
    }

    /// The app never builds a provider URL or names a Google scope: it opens what the backend returns.
    @Test func appNeverBuildsAGoogleAuthorizationURL() throws {
        for file in IdentityGuardTests.appFiles() where file.pathExtension == "swift" && file.lastPathComponent != "FixtureBackend.swift" {
            let text = try String(contentsOf: file, encoding: .utf8)
            #expect(!text.contains("accounts.google.com"), "\(file.lastPathComponent) builds a Google URL")
            #expect(!text.contains("googleapis.com/auth/"), "\(file.lastPathComponent) names a Google scope")
            #expect(!text.contains("gmail.modify") && !text.contains("gmail.metadata") && !text.contains("mail.google.com"))
        }
        #expect(FixtureBackend.gmailScope == "https://www.googleapis.com/auth/gmail.readonly")
    }

    // MARK: Contract

    @Test func candidatesArriveInAnItemsEnvelope() async throws {
        let json = #"{"status":"ok","items":[{"email_id":1,"candidate_id":7,"amount":25,"currency":"USD","account_base_currency":"CRC","review_status":"pending","transaction_type":"expense","extra":{"x":1}}]}"#
        let transport = ScriptedTransport([.status(200, json)])
        let list = try await DincrService(client: client(transport)).mailCandidates(pendingOnly: true)
        #expect(list.count == 1 && list[0].candidateId == 7 && list[0].needsRate)
        let query = URLComponents(url: transport.requests[0].url!, resolvingAgainstBaseURL: false)?.queryItems
        #expect(query == [URLQueryItem(name: "status", value: "pending")])
        #expect(transport.requests[0].url?.path == "/user-product/vip/gmail/emails")
    }

    @Test func syncFailedConnectionsIsAList() async throws {
        let json = #"{"status":"partial","connections":2,"failed_connections":[3],"scan_scope":"year_to_date","initial_scan_complete":true,"found":4,"auto_saved":0,"pending":2,"payroll_reports":0,"duplicates":1}"#
        let result = try await DincrService(client: client(ScriptedTransport([.status(200, json)]))).syncMail()
        #expect(result.failedConnections == [3])
        #expect(result.pending == 2 && result.duplicates == 1)
    }

    @Test func statusHidesDisabledMailboxesAndFailsClosedOnConsent() throws {
        let json = #"{"connected":true,"connections":[{"id":1,"status":"active","google_email":"a@b.test"},{"id":2,"status":"disabled"},{"id":3,"status":"reauthorization_required"}],"consent":{"required":false,"version":"v2"}}"#
        let status = try APIClient.decoder.decode(MailStatus.self, from: Data(json.utf8))
        #expect(status.mailboxes.map(\.id) == [1, 3])
        #expect(status.mailboxes[1].needsReconnect)
        #expect(!status.consentRequired)
        let silent = try APIClient.decoder.decode(MailStatus.self, from: Data(#"{"connected":false}"#.utf8))
        #expect(silent.consentRequired, "no consent information means consent is required")
    }

    @Test func connectSendsTheScopeAndTheAppLanguage() async throws {
        let transport = ScriptedTransport([.status(200, #"{"authorization_url":"https://accounts.example.test/o/oauth2/v2/auth?x=1"}"#)])
        let url = try await DincrService(client: client(transport)).connectMail(.gmail, MailConnectRequest(scope: .currentMonth, language: .spanish))
        #expect(url.host == "accounts.example.test")
        let body = try Self.body(transport.requests[0])
        #expect(body["import_scope"] as? String == "current_month")
        #expect(body["locale"] as? String == "es")
        #expect(transport.requests[0].url?.path == "/user-product/vip/gmail/connect")
        #expect(transport.requests[0].value(forHTTPHeaderField: "Accept-Language") == "es")
    }

    @Test func aNonHTTPSAuthorizationURLIsRefused() async throws {
        let transport = ScriptedTransport([.status(200, #"{"authorization_url":"javascript:alert(1)"}"#)])
        await #expect(throws: APIError.self) { _ = try await DincrService(client: client(transport)).connectMail(.gmail, MailConnectRequest(scope: .currentYear, language: .english)) }
    }

    @Test func consentSendsTheServerVersionAndDisconnectUsesTheQuery() async throws {
        let transport = ScriptedTransport([.status(200, #"{"status":"accepted"}"#), .status(200, #"{"status":"disconnected"}"#)])
        let service = DincrService(client: client(transport))
        try await service.acceptMailConsent(version: "mail-monitor-2026-09-v2")
        #expect(try Self.body(transport.requests[0])["version"] as? String == "mail-monitor-2026-09-v2")
        #expect(try Self.body(transport.requests[0])["accepted"] as? Bool == true)
        try await service.disconnectMail(connectionID: 5)
        #expect(transport.requests[1].httpMethod == "DELETE")
        #expect(transport.requests[1].url?.query == "connection_id=5")
        #expect(transport.requests[1].httpBody == nil)
    }

    @Test func correctionSendsCategoryAlwaysAndRateOnlyWhenNeeded() async throws {
        let transport = ScriptedTransport([.status(200, #"{"status":"confirmed","candidate_id":7,"transaction_id":9}"#), .status(200, #"{"status":"confirmed"}"#)])
        let service = DincrService(client: client(transport))
        _ = try await service.correctCandidate(id: 7, CandidateCorrection(transactionDate: "2026-09-01", description: "x", amount: Decimal(string: "25.5")!, transactionType: "expense", category: "Compras", exchangeRate: Decimal(string: "507.25")!))
        let first = try Self.body(transport.requests[0])
        #expect(transport.requests[0].httpMethod == "PUT")
        #expect(first["category"] as? String == "Compras")
        #expect((first["exchange_rate"] as? NSNumber)?.decimalValue == Decimal(string: "507.25"))
        #expect(first["currency"] == nil, "the backend takes the notice's own currency")
        _ = try await service.correctCandidate(id: 7, CandidateCorrection(transactionDate: "2026-09-01", description: "x", amount: 10, transactionType: "expense", category: "general", exchangeRate: nil))
        #expect(try Self.body(transport.requests[1])["exchange_rate"] == nil)
    }

    @Test func invalidCorrectionsNeverLeaveTheDevice() async throws {
        let service = DincrService(client: client(ScriptedTransport([])))
        let bad: [CandidateCorrection] = [
            CandidateCorrection(transactionDate: "2026-09-01", description: "x", amount: 0, transactionType: "expense", category: "g", exchangeRate: nil),
            CandidateCorrection(transactionDate: "2026-13-01", description: "x", amount: 1, transactionType: "expense", category: "g", exchangeRate: nil),
            CandidateCorrection(transactionDate: "2026-09-01", description: "x", amount: 1, transactionType: "expense", category: "g", exchangeRate: 0),
            CandidateCorrection(transactionDate: "2026-09-01", description: "x", amount: 1, transactionType: "expense", category: "g", exchangeRate: 100_001),
            CandidateCorrection(transactionDate: "2026-09-01", description: "x", amount: 1, transactionType: "expense", category: "g", exchangeRate: Decimal(string: "1.0000001")!),
        ]
        for correction in bad {
            await #expect(throws: APIError.self) { _ = try await service.correctCandidate(id: 1, correction) }
        }
    }

    // MARK: Currency of a notice

    @Test func noticeMoneyUsesTheOriginalPairAndTheBackendDefaultBase() throws {
        let converted = try APIClient.decoder.decode(MailCandidate.self, from: Data(#"{"candidate_id":1,"amount":12700,"currency":"CRC","original_amount":25,"original_currency":"USD","account_base_currency":"CRC"}"#.utf8))
        #expect(converted.nativeCurrency == "USD" && converted.nativeAmount == 25 && converted.needsRate)
        let noBase = try APIClient.decoder.decode(MailCandidate.self, from: Data(#"{"candidate_id":2,"amount":25,"currency":"USD"}"#.utf8))
        #expect(noBase.needsRate, "a missing base is CRC, like candidate_currency.py")
        let euro = try APIClient.decoder.decode(MailCandidate.self, from: Data(#"{"candidate_id":3,"amount":12,"currency":"EUR","account_base_currency":"CRC"}"#.utf8))
        #expect(euro.cannotConvert && !euro.needsRate)
        let local = try APIClient.decoder.decode(MailCandidate.self, from: Data(#"{"candidate_id":4,"amount":100,"currency":"CRC","account_base_currency":"CRC"}"#.utf8))
        #expect(!local.needsRate && !local.cannotConvert)
    }

    // MARK: Return deep link

    @Test func returnLinksAreParsedStrictly() {
        let schemes: Set<String> = ["com.dincr.app", "com.finva.app"]
        let good = MailReturn.parse(URL(string: "com.finva.app://gmail/callback?gmail=authorized&flow=f1&completion=c1&ret=r1")!, schemes: schemes)
        #expect(good?.provider == .gmail && good?.isAuthorized == true && good?.flow == "f1" && good?.completion == "c1")
        #expect(MailReturn.parse(URL(string: "com.dincr.app://gmail/callback?microsoft=denied&ret=r")!, schemes: schemes)?.isAuthorized == false)
        let rejected = [
            "evil.app://gmail/callback?gmail=authorized&flow=f&completion=c",
            "com.finva.app://auth/callback?gmail=authorized&flow=f&completion=c",
            "com.finva.app://gmail/callbackX?gmail=authorized&flow=f&completion=c",
            "com.finva.app://gmail/callback?gmail=authorized&microsoft=authorized",
            "com.finva.app://gmail/callback?gmail=authorized&flow=a&flow=b&completion=c",
            "com.finva.app://gmail/callback#gmail=authorized",
            "com.finva.app://gmail:1/callback?gmail=authorized",
            "com.finva.app://gmail/callback?gmail=authorized&flow=a%0Ab&completion=c",
            "com.finva.app://gmail/callback",
        ]
        for text in rejected { #expect(MailReturn.parse(URL(string: text)!, schemes: schemes) == nil, "\(text)") }
        #expect(MailReturn.parse(URL(string: "com.finva.app://gmail/callback?gmail=authorized&flow=f")!, schemes: schemes)?.isAuthorized == false,
                "no completion: nothing to redeem")
    }

    @Test func handledReturnsAreRedeemedOnce() {
        var ledger = HandledReturns(capacity: 2)
        ledger.add("a"); ledger.add("a"); ledger.add("b"); ledger.add("c")
        #expect(ledger.keys == ["b", "c"])
        #expect(ledger.contains("c") && !ledger.contains("a"))
    }

    // MARK: Review invariants (fixture backend mirrors gmail_service.review_candidate)

    @Test func acceptTwiceSavesOneTransactionAndRejectSavesNone() async throws {
        let service = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero))
        let before = try await service.movements().count
        let pending = try await service.mailCandidates(pendingOnly: true)
        let local = try #require(pending.first { !$0.needsRate && !$0.cannotConvert })
        let first = try await service.acceptCandidate(id: local.candidateId!)
        let second = try await service.acceptCandidate(id: local.candidateId!)
        #expect(first.status == "confirmed" && first.alreadyReviewed != true)
        #expect(second.alreadyReviewed == true && second.transactionId == first.transactionId)
        #expect(try await service.movements().count == before + 1, "a second accept must not duplicate")
        let foreign = try #require(pending.first { $0.cannotConvert })
        let rejected = try await service.rejectCandidate(id: foreign.candidateId!)
        #expect(rejected.status == "rejected" && rejected.transactionId == nil)
        #expect(try await service.movements().count == before + 1, "reject never creates a transaction")
        #expect(try await service.acceptCandidate(id: foreign.candidateId!).alreadyReviewed == true, "a rejected notice cannot become a transaction")
    }

    @Test func aDollarNoticeNeedsTheUsersRate() async throws {
        let service = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero))
        let dollar = try #require(try await service.mailCandidates(pendingOnly: true).first { $0.needsRate })
        await #expect(throws: APIError.self) { _ = try await service.acceptCandidate(id: dollar.candidateId!) }
        let saved = try await service.correctCandidate(id: dollar.candidateId!, CandidateCorrection(transactionDate: "2026-09-01", description: "Tienda", amount: 25,
                                                                                                  transactionType: "expense", category: "Compras", exchangeRate: Decimal(string: "507.5")!))
        #expect(saved.status == "confirmed")
    }

    @Test func mailIsVipOnlyOnTheServer() async throws {
        let service = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .basic, latency: .zero))
        do {
            _ = try await service.mailStatus()
            Issue.record("a Basic account must not reach the Email Monitor")
        } catch let error as APIError {
            #expect(error.status == 403 && error.kind == .forbidden)
        }
        let free = FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .free, latency: .zero))
        await #expect(throws: APIError.self) { _ = try await free.budget() }
    }

    // MARK: Google OAuth video readiness (fixture end to end; the real provider is DEVICE REQUIRED)

    /// Email Monitor → explanation → consent → Connect Gmail → provider (gmail.readonly) → return to
    /// DINCR → one-time completion → mailbox connected → sync → candidates. Same requests and parsing
    /// as against the real backend; only the provider page is simulated.
    @Test func connectFlowEndToEndOnTheFixtureBackend() async throws {
        let backend = FixtureBackend(scenario: .mailOnboarding, latency: .zero)
        let service = FixtureBackend.service(backend)
        var status = try await service.mailStatus()
        #expect(!status.isConnected && status.consentRequired)
        await #expect(throws: APIError.self) { _ = try await service.connectMail(.gmail, MailConnectRequest(scope: .currentYear, language: .spanish)) }
        try await service.acceptMailConsent(version: try #require(status.consent?.version))
        let authorize = try await service.connectMail(.gmail, MailConnectRequest(scope: .currentYear, language: .spanish))
        let items = URLComponents(url: authorize, resolvingAgainstBaseURL: false)?.queryItems ?? []
        #expect(items.first { $0.name == "scope" }?.value == "https://www.googleapis.com/auth/gmail.readonly")
        #expect(items.first { $0.name == "hl" }?.value == "es")
        let back = try #require(items.first { $0.name == "fixture_return" }?.value.flatMap(URL.init(string:)))
        let mailReturn = try #require(MailReturn.parse(back, schemes: ["com.dincr.app", "com.finva.app"]))
        #expect(mailReturn.isAuthorized)
        let completed = try await service.completeMailConnection(flow: mailReturn.flow!, completion: mailReturn.completion!)
        #expect(completed.status == "connected")
        await #expect(throws: APIError.self, "a completion is single-use") {
            _ = try await service.completeMailConnection(flow: mailReturn.flow!, completion: mailReturn.completion!)
        }
        status = try await service.mailStatus()
        #expect(status.isConnected && !status.mailboxes.isEmpty)
        let sync = try await service.syncMail()
        #expect((sync.found ?? 0) > 0 && sync.failedConnections == [])
        let pending = try await service.mailCandidates(pendingOnly: true)
        #expect(!pending.isEmpty)
    }
}

/// Currency entry and edit rules shared with Android (#269).
@Suite struct CurrencyEditTests {
    static func movement(_ json: String) throws -> Movement { try APIClient.decoder.decode(Movement.self, from: Data(json.utf8)) }

    @Test func aCompleteForeignManualRowIsEditableInItsCurrency() throws {
        let row = try Self.movement(#"{"movement_id":"expense:13","origin":"expense","transaction_date":"2026-09-01","amount":5075,"transaction_type":"expense","editable":true,"original_amount":10,"original_currency":"USD","exchange_rate":507.5}"#)
        #expect(!row.isEditable, "the base-currency editor would erase original_*")
        #expect(row.isCurrencyEditable(entryCurrencies: ["CRC", "USD"]))
        #expect(!row.isCurrencyEditable(entryCurrencies: ["CRC"]), "a currency the backend doesn't convert stays read-only")
        let mail = try Self.movement(#"{"movement_id":"transaction:9","origin":"transaction","transaction_date":"2026-09-01","amount":5075,"transaction_type":"expense","editable":true,"original_amount":10,"original_currency":"USD","exchange_rate":507.5}"#)
        #expect(!mail.canEdit(entryCurrencies: ["CRC", "USD"]), "mail rows never switch currency")
        let partial = try Self.movement(#"{"movement_id":"expense:14","origin":"expense","transaction_date":"2026-09-01","amount":5075,"transaction_type":"expense","editable":true,"original_currency":"USD"}"#)
        #expect(!partial.canEdit(entryCurrencies: ["CRC", "USD"]), "partial currency data stays read-only")
    }

    @Test func ratesAreTheUsersOwnAndBounded() {
        #expect(RateInput.parse("507,5", separators: .dotComma) == Decimal(string: "507.5"))
        #expect(RateInput.parse("507.123456", separators: .commaDot) == Decimal(string: "507.123456"))
        for bad in ["0", "", "-1", "507,1234567", "100.001", "1e3", "abc"] {
            #expect(RateInput.parse(bad, separators: .dotComma) == nil, "\(bad)")
        }
        #expect(ConversionPreview.baseAmount(typed: 10, currency: "USD", base: "CRC", rate: Decimal(string: "507.5")) == 5075)
        #expect(ConversionPreview.baseAmount(typed: 5075, currency: "CRC", base: "USD", rate: Decimal(string: "507.5")) == 10)
        #expect(ConversionPreview.baseAmount(typed: 10, currency: "EUR", base: "CRC", rate: 1) == nil)
    }

    @Test func aForeignEntryWithoutARateNeverLeavesTheDevice() async throws {
        let service = DincrService(client: APIClient(baseURL: URL(string: "https://api.example.test")!, tokens: CountingTokens(), transport: ScriptedTransport([]), backoff: { _ in }))
        await #expect(throws: APIError.self) {
            try await service.create(.expense, EntryCreate(amount: 10, description: "x", category: "c", entryDate: "2026-09-01", currency: "USD", exchangeRate: nil), idempotencyKey: "op_12345678")
        }
    }

    @Test func entryBodyCarriesCurrencyOnlyWhenForeign() throws {
        let base = try JSONSerialization.jsonObject(with: APIClient.encoder.encode(EntryCreate(amount: 10, description: "x", category: "c", entryDate: nil))) as? [String: Any]
        #expect(base?["currency"] == nil && base?["exchange_rate"] == nil)
        let foreign = try JSONSerialization.jsonObject(with: APIClient.encoder.encode(EntryCreate(amount: 10, description: "x", category: "c", entryDate: nil, currency: "USD", exchangeRate: 507))) as? [String: Any]
        #expect(foreign?["currency"] as? String == "USD" && (foreign?["exchange_rate"] as? NSNumber)?.intValue == 507)
    }

    @Test func retryingAnAmountReusesItsKey() {
        var minted = 0
        var submission = AmountSubmission { minted += 1; return "op_key_\(minted)" }
        let first = submission.key(for: 50_000)
        #expect(submission.key(for: Decimal(string: "50000.00")!) == first)
        #expect(submission.key(for: 40_000) != first)
        #expect(minted == 2)
    }
}
