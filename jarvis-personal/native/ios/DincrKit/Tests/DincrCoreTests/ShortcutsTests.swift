import Foundation
import Security
import Testing
@testable import DincrCore

/// Perfil → Atajos de iPhone and the two background App Intents: amount parsing, the Keychain item,
/// the capture requests (shortcut token only, Idempotency-Key, amount as a string) and their answers,
/// and linking against the fixture backend. Synthetic data only.
@Suite struct ShortcutAmountTests {
    private func parse(_ text: String, _ fallback: ShortcutCurrency = .crc) -> ShortcutAmount? {
        try? ShortcutAmount.parse(text, fallback: fallback).get()
    }

    private func failure(_ text: String) -> ShortcutAmount.Failure? {
        if case .failure(let failure) = ShortcutAmount.parse(text, fallback: .crc) { return failure }
        return nil
    }

    @Test func readsTheShapesShortcutsMayDeliver() {
        let cases: [(String, ShortcutCurrency, String, ShortcutCurrency)] = [
            ("₡12.500,00", .usd, "12500.00", .crc),
            ("CRC 12,500.00", .usd, "12500.00", .crc),
            ("$4.99", .crc, "4.99", .usd),
            ("4,99 US$", .crc, "4.99", .usd),
            ("USD 1,234.5", .crc, "1234.5", .usd),
            ("12500", .crc, "12500", .crc),
            ("12500.5", .crc, "12500.5", .crc),
            ("4.99", .usd, "4.99", .usd),
            ("12,500", .crc, "12500", .crc),
            ("1.234.567,89", .crc, "1234567.89", .crc),
            ("1 234 567,89 ₡", .crc, "1234567.89", .crc),
            ("₡\u{00A0}8\u{202F}000", .crc, "8000", .crc),
            ("  0,50  ", .crc, "0.50", .crc),
            ("007", .crc, "7", .crc),
            ("crc 3000", .usd, "3000", .crc),
            ("+15", .crc, "15", .crc),
        ]
        for (text, fallback, wire, currency) in cases {
            let parsed = parse(text, fallback)
            #expect(parsed?.wire == wire, "\(text)")
            #expect(parsed?.currency == currency, "\(text)")
            #expect(parsed?.value == Decimal(string: wire, locale: Locale(identifier: "en_US_POSIX")), "\(text)")
        }
    }

    @Test func theWireAlwaysMatchesTheBackendPattern() {
        for text in ["₡12.500,00", "$4.99", "1", "9.9", "50000000", "12,345"] {
            let wire = parse(text)?.wire ?? ""
            #expect(wire.range(of: #"^\d{1,10}(\.\d{1,2})?$"#, options: .regularExpression) != nil, "\(text) → \(wire)")
        }
    }

    @Test func withoutAMarkTheMonedaParameterDecides() {
        #expect(parse("25", .usd)?.currency == .usd)
        #expect(parse("25", .crc)?.currency == .crc)
    }

    @Test func refusesWhatItCannotReadForSure() {
        #expect(failure("") == .empty)
        #expect(failure("   ") == .empty)
        for text in ["abc", "12a", "₡", "1.234.56", "1,234.567", "1234.567", "12.", ".5", "1..2", "1,2,3", "12 500 y 300", "٤٫٩٩", "1e5", "NaN", "12.500,000"] {
            #expect(failure(text) == .unreadable, "\(text)")
        }
        #expect(failure("₡12 ($3)") == .mixedCurrencies)
        #expect(failure("CRC 5 USD") == .mixedCurrencies)
    }

    @Test func refusesZeroNegativeAndAbsurdAmounts() {
        #expect(failure("0") == .notPositive)
        #expect(failure("0,00") == .notPositive)
        #expect(failure("-4.99") == .notPositive)
        #expect(failure("−₡500") == .notPositive)
        #expect(failure("₡50.000.000,01") == .tooLarge)
        #expect(failure("$100,000.01") == .tooLarge)
        #expect(parse("₡50.000.000")?.wire == "50000000")
        #expect(parse("$100,000.00")?.wire == "100000.00")
        #expect(failure("12345678901") == .unreadable, "more than ten integer digits")
    }

    @Test func failuresHaveSpanishMessages() {
        for failure in [ShortcutAmount.Failure.empty, .unreadable, .notPositive, .tooLarge, .mixedCurrencies] {
            #expect(!failure.message(.spanish).isEmpty && !failure.message(.english).isEmpty)
        }
        #expect(ShortcutAmount.Failure.notPositive.message(.spanish) == "El monto de la compra tiene que ser mayor a cero.")
    }
}

@Suite struct ShortcutTokenStoreTests {
    @Test func theKeychainItemWorksLockedButNeverLeavesTheDevice() {
        let item = KeychainShortcutTokenStore().item(data: Data("x".utf8))
        #expect(item[kSecAttrAccessible as String] as? String == kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly as String)
        #expect(item[kSecAttrSynchronizable as String] as? Bool == false)
        #expect(item[kSecAttrService as String] as? String == "com.dincr.app.shortcuts")
        #expect(item[kSecAttrService as String] as? String != KeychainSessionStore().service, "its own item, not the session's")
    }

    @Test func theInMemoryStoreSavesReadsAndClears() {
        let store = InMemoryShortcutTokenStore()
        #expect(!store.isLinked && store.read() == nil)
        store.save(ShortcutCredential(token: "dsc_abc-DEF_123", accountID: 7))
        #expect(store.isLinked && store.read() == ShortcutCredential(token: "dsc_abc-DEF_123", accountID: 7))
        store.clear()
        #expect(!store.isLinked)
    }

    @Test func onlyWellFormedTokensAreKept() {
        for token in ["dsc_a", "dsc_abc-DEF_123"] { #expect(ShortcutCredential.isValidToken(token), "\(token)") }
        for token in ["", "dsc_", "abc", "Bearer dsc_a", "dsc_a b", "dsc_a/b", "dsc_ñ", "dsc_a=", "DSC_abc"] {
            #expect(!ShortcutCredential.isValidToken(token), "\(token)")
        }
        let store = InMemoryShortcutTokenStore()
        store.save(ShortcutCredential(token: "not a token", accountID: 1))
        #expect(!store.isLinked)
    }
}

@Suite struct ShortcutSenderTests {
    static let token = "dsc_synthetic_token"
    static let key = "6F1C2B9E-0D4A-4F7E-9A51-2C8D7E3B4A10"

    private func sender(_ transport: ScriptedTransport) -> ShortcutSender {
        ShortcutSender(baseURL: URL(string: "https://api.example.test")!, transport: transport, language: .spanish, backoff: {})
    }

    private func purchase(_ amount: String = "₡12.500,50", card: String? = "Tarjeta de ejemplo") -> ShortcutPurchase {
        ShortcutPurchase(amount: try! ShortcutAmount.parse(amount, fallback: .crc).get(), merchant: " Comercio de ejemplo ", card: card)
    }

    @Test func aPurchaseCarriesOnlyTheShortcutTokenTheKeyAndAStringAmount() async throws {
        let transport = ScriptedTransport([.status(201, #"{"status":"created"}"#)])
        let result = try await sender(transport).send(purchase(), token: Self.token, idempotencyKey: Self.key)
        #expect(result == .created)
        let request = try #require(transport.requests.first)
        #expect(request.httpMethod == "POST")
        #expect(request.url?.absoluteString == "https://api.example.test/user-product/vip/shortcuts/apple-pay")
        #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer \(Self.token)")
        #expect(request.value(forHTTPHeaderField: "Idempotency-Key") == Self.key)
        #expect(request.value(forHTTPHeaderField: "X-Idempotency-Key") == nil)
        #expect(request.value(forHTTPHeaderField: "Content-Type") == "application/json")
        let body = String(decoding: try #require(request.httpBody), as: UTF8.self)
        #expect(body == #"{"amount":"12500.50","card":"Tarjeta de ejemplo","currency":"CRC","merchant":"Comercio de ejemplo"}"#)
    }

    @Test func aPurchaseWithoutCardSendsAnExplicitNullAndCutsLongTexts() throws {
        let long = ShortcutPurchase(amount: try ShortcutAmount.parse("1", fallback: .usd).get(), merchant: String(repeating: "m", count: 200), card: String(repeating: "c", count: 90))
        #expect(long.merchant.count == 120 && long.card?.count == 60)
        let none = purchase(card: "   ")
        #expect(none.card == nil)
        let body = String(decoding: try APIClient.encoder.encode(none), as: UTF8.self)
        #expect(body.contains(#""card":null"#))
    }

    @Test func aBankMessageGoesToItsRouteWithTheSameHeaders() async throws {
        let transport = ScriptedTransport([.status(200, #"{"status":"not_recognized"}"#)])
        let result = try await sender(transport).send(ShortcutBankMessage(text: "  Aviso sintético de compra  "), token: Self.token, idempotencyKey: Self.key)
        #expect(result == .notRecognized)
        let request = try #require(transport.requests.first)
        #expect(request.url?.path == "/user-product/vip/shortcuts/bank-sms")
        #expect(request.value(forHTTPHeaderField: "Authorization") == "Bearer \(Self.token)")
        #expect(request.value(forHTTPHeaderField: "Idempotency-Key") == Self.key)
        #expect(String(decoding: try #require(request.httpBody), as: UTF8.self) == #"{"text":"Aviso sintético de compra"}"#)
    }

    @Test func answersMapToResultsAndErrors() async {
        let cases: [(Int, String, Result<ShortcutCaptureResult, ShortcutCaptureError>)] = [
            (201, #"{"status":"created"}"#, .success(.created)),
            (201, "{}", .success(.created)),
            (200, #"{"status":"already_received"}"#, .success(.alreadyReceived)),
            (200, #"{"status":"not_recognized"}"#, .success(.notRecognized)),
            (200, #"{"status":"something_new"}"#, .failure(.server)),
            (401, #"{"detail":"x"}"#, .failure(.tokenRejected)),
            (403, #"{"detail":"x"}"#, .failure(.planNotIncluded)),
            (422, #"{"detail":"El comercio es obligatorio."}"#, .failure(.rejected("El comercio es obligatorio."))),
            (422, #"{"detail":[{"loc":["body"]}]}"#, .failure(.rejected(nil))),
            (429, "{}", .failure(.tooMany)),
            (500, "{}", .failure(.server)),
        ]
        for (status, body, expected) in cases {
            let transport = ScriptedTransport([.status(status, body)])
            let got: Result<ShortcutCaptureResult, ShortcutCaptureError>
            do { got = .success(try await sender(transport).send(purchase(), token: Self.token, idempotencyKey: Self.key)) } catch { got = .failure(error) }
            #expect(got == expected, "\(status) \(body)")
            #expect(transport.requests.count == 1, "\(status) is not retried")
        }
    }

    @Test func aTransientFailureIsRetriedOnceWithTheSameKey() async throws {
        let transport = ScriptedTransport([.failure(.networkConnectionLost), .status(200, #"{"status":"already_received"}"#)])
        #expect(try await sender(transport).send(purchase(), token: Self.token, idempotencyKey: Self.key) == .alreadyReceived)
        #expect(transport.requests.map { $0.value(forHTTPHeaderField: "Idempotency-Key") } == [Self.key, Self.key])

        let down = ScriptedTransport([.status(503, "{}"), .status(503, "{}")])
        await #expect(throws: ShortcutCaptureError.server) { try await sender(down).send(purchase(), token: Self.token, idempotencyKey: Self.key) }
        #expect(down.requests.count == 2)

        let offline = ScriptedTransport([.failure(.notConnectedToInternet), .failure(.notConnectedToInternet), .status(201, "{}")])
        await #expect(throws: ShortcutCaptureError.offline) { try await sender(offline).send(purchase(), token: Self.token, idempotencyKey: Self.key) }
        #expect(offline.requests.count == 2)
    }

    @Test func nothingLeavesWithoutAValidTokenOrKey() async {
        let transport = ScriptedTransport([])
        await #expect(throws: ShortcutCaptureError.notLinked) { try await sender(transport).send(purchase(), token: "fixture-session", idempotencyKey: Self.key) }
        await #expect(throws: ShortcutCaptureError.server) { try await sender(transport).send(purchase(), token: Self.token, idempotencyKey: "short") }
        #expect(transport.requests.isEmpty)
        #expect(ShortcutSender.isValidIdempotencyKey(ShortcutSender.newIdempotencyKey()))
        for key in ["1234567", String(repeating: "a", count: 129), "abc def gh", "abcdefgh!"] { #expect(!ShortcutSender.isValidIdempotencyKey(key), "\(key)") }
    }

    @Test func errorMessagesAreSpanishAndPlain() {
        #expect(ShortcutCaptureError.notLinked.message(.purchase, .spanish) == "Activá Atajos de iPhone en DINCR → Perfil.")
        #expect(ShortcutCaptureError.tokenRejected.message(.bankMessage, .spanish) == "Activá Atajos de iPhone en DINCR → Perfil.")
        #expect(ShortcutCaptureError.planNotIncluded.message(.purchase, .spanish) == "Tu plan no incluye Atajos de iPhone.")
        #expect(ShortcutCaptureError.offline.message(.purchase, .spanish) == "No pudimos enviar la compra. Revisá tu conexión.")
        #expect(ShortcutCaptureError.rejected("Detalle").message(.purchase, .english) != "Detalle", "Spanish details only for Spanish sessions")
        #expect(ShortcutCaptureResult.created.purchaseMessage(.spanish) == "Compra enviada a DINCR para revisar.")
        #expect(ShortcutCaptureResult.alreadyReceived.purchaseMessage(.spanish) == "Ya la habíamos recibido.")
        #expect(ShortcutCaptureResult.notRecognized.bankMessageMessage(.spanish) == "DINCR no reconoció este aviso.")
        for text in [ShortcutCaptureError.server.message(.purchase, .spanish), ShortcutCaptureResult.created.bankMessageMessage(.spanish)] {
            #expect(!text.localizedCaseInsensitiveContains("jarvis") && !text.localizedCaseInsensitiveContains("finva"))
        }
    }
}

@Suite struct ShortcutCaptureClientTests {
    private func client(_ store: ShortcutTokenStore, _ transport: ScriptedTransport) -> ShortcutCaptureClient {
        ShortcutCaptureClient(store: store, sender: ShortcutSender(baseURL: URL(string: "https://api.example.test")!, transport: transport, language: .spanish, backoff: {}),
                              language: .spanish)
    }

    @Test func withoutATokenNothingIsSent() async {
        let transport = ScriptedTransport([])
        await #expect(throws: ShortcutCaptureError.notLinked) {
            try await client(InMemoryShortcutTokenStore(), transport).registerPurchase(amount: "100", currency: .crc, merchant: "Comercio", card: nil)
        }
        await #expect(throws: ShortcutCaptureError.notLinked) { try await client(InMemoryShortcutTokenStore(), transport).sendBankMessage("Compra") }
        #expect(transport.requests.isEmpty)
    }

    @Test func invalidInputIsRefusedBeforeSending() async {
        let store = InMemoryShortcutTokenStore(ShortcutCredential(token: "dsc_synthetic", accountID: 1))
        let transport = ScriptedTransport([])
        await #expect(throws: ShortcutCaptureError.invalidInput("El monto de la compra tiene que ser mayor a cero.")) {
            try await client(store, transport).registerPurchase(amount: "0", currency: .crc, merchant: "Comercio", card: nil)
        }
        await #expect(throws: ShortcutCaptureError.invalidInput("Falta el comercio de la compra.")) {
            try await client(store, transport).registerPurchase(amount: "100", currency: .crc, merchant: "  ", card: nil)
        }
        await #expect(throws: ShortcutCaptureError.invalidInput("Falta el texto del mensaje.")) { try await client(store, transport).sendBankMessage(" \n ") }
        await #expect(throws: ShortcutCaptureError.self) { try await client(store, transport).sendBankMessage(String(repeating: "a", count: 1001)) }
        #expect(transport.requests.isEmpty)
    }

    @Test func aRevokedTokenIsForgotten() async {
        let store = InMemoryShortcutTokenStore(ShortcutCredential(token: "dsc_synthetic", accountID: 1))
        await #expect(throws: ShortcutCaptureError.tokenRejected) {
            try await client(store, ScriptedTransport([.status(401, "{}")])).sendBankMessage("Compra sintética")
        }
        #expect(!store.isLinked)
        let kept = InMemoryShortcutTokenStore(ShortcutCredential(token: "dsc_synthetic", accountID: 1))
        await #expect(throws: ShortcutCaptureError.planNotIncluded) {
            try await client(kept, ScriptedTransport([.status(403, "{}")])).sendBankMessage("Compra sintética")
        }
        #expect(kept.isLinked, "a plan refusal does not unlink")
    }
}

@Suite struct ShortcutLinkingTests {
    private func setup(plan: PlanTier = .vip, role: FixtureBackend.Role = .user) -> (FixtureBackend, DincrService) {
        let backend = FixtureBackend(scenario: .populated, plan: plan, role: role, latency: .zero)
        return (backend, FixtureBackend.service(backend))
    }

    @Test func reconcileKeepsTheKeychainHonest() {
        let mine = ShortcutCredential(token: "dsc_a", accountID: 1)
        let other = ShortcutCredential(token: "dsc_b", accountID: 2)
        #expect(ShortcutLinking.reconcile(serverLinked: true, local: mine, accountID: 1) == (.linked, false))
        #expect(ShortcutLinking.reconcile(serverLinked: true, local: nil, accountID: 1) == (.linkedElsewhere, false))
        #expect(ShortcutLinking.reconcile(serverLinked: false, local: mine, accountID: 1) == (.notLinked, true))
        #expect(ShortcutLinking.reconcile(serverLinked: false, local: nil, accountID: 1) == (.notLinked, false))
        #expect(ShortcutLinking.reconcile(serverLinked: true, local: other, accountID: 1) == (.linkedElsewhere, true))
    }

    @Test func onlyVipAndTheOwnerReachIt() {
        #expect(ShortcutLinking.isAvailable(to: Profile(id: 1, role: "owner", subscription: nil)))
        #expect(ShortcutLinking.isAvailable(to: Profile(id: 2, subscription: .init(plan: "vip", status: "active"))))
        for plan in ["free", "basic"] { #expect(!ShortcutLinking.isAvailable(to: Profile(id: 3, subscription: .init(plan: plan, status: "active")))) }
        #expect(!ShortcutLinking.isAvailable(to: nil))
    }

    @Test func activateSendAndDeactivateOnTheFixtureBackend() async throws {
        let (backend, service) = setup()
        let store = InMemoryShortcutTokenStore()
        let linking = ShortcutLinking(service: service, store: store)
        #expect(try await linking.status(accountID: 4201) == .notLinked)
        #expect(try await linking.activate(accountID: 4201) == .linked)
        #expect(store.read()?.accountID == 4201)
        #expect(try await linking.status(accountID: 4201) == .linked)

        let capture = ShortcutCaptureClient(store: store, sender: ShortcutSender(baseURL: FixtureBackend.baseURL, transport: backend, language: .spanish, backoff: {}))
        let key = ShortcutSender.newIdempotencyKey()
        #expect(try await capture.registerPurchase(amount: "₡12.500,00", currency: .usd, merchant: "Comercio de ejemplo", card: nil, idempotencyKey: key) == .created)
        #expect(try await capture.registerPurchase(amount: "₡12.500,00", currency: .usd, merchant: "Comercio de ejemplo", card: nil, idempotencyKey: key) == .alreadyReceived)
        #expect(try await capture.sendBankMessage("Saludo sin datos") == .notRecognized)
        #expect(await backend.shortcutCaptureCount == 2)
        // The capture request never carried the app session.
        let captures = await backend.requests.filter { $0.url?.path.hasSuffix("/apple-pay") == true }
        #expect(captures.allSatisfy { $0.value(forHTTPHeaderField: "Authorization")?.hasPrefix("Bearer dsc_") == true })

        #expect(try await linking.deactivate() == .notLinked)
        #expect(!store.isLinked)
        #expect(try await linking.status(accountID: 4201) == .notLinked)
    }

    @Test func issuingAgainRevokesTheOldTokenAndAnotherDeviceSeesItElsewhere() async throws {
        let (backend, service) = setup()
        let first = InMemoryShortcutTokenStore()
        let second = InMemoryShortcutTokenStore()
        _ = try await ShortcutLinking(service: service, store: first).activate(accountID: 4201)
        _ = try await ShortcutLinking(service: service, store: second).activate(accountID: 4201)
        let old = ShortcutCaptureClient(store: first, sender: ShortcutSender(baseURL: FixtureBackend.baseURL, transport: backend, backoff: {}))
        await #expect(throws: ShortcutCaptureError.tokenRejected) { try await old.sendBankMessage("Compra sintética") }
        #expect(!first.isLinked)
        #expect(try await ShortcutLinking(service: service, store: first).status(accountID: 4201) == .linkedElsewhere)
    }

    @Test func freeAndBasicAreRefusedAndTheOwnerIsAllowed() async throws {
        for plan in [PlanTier.free, .basic] {
            let (_, service) = setup(plan: plan)
            await #expect(throws: APIError.self) { try await service.issueShortcutToken() }
        }
        let (_, owner) = setup(role: .owner)
        #expect(ShortcutCredential.isValidToken(try await owner.issueShortcutToken().token))
    }

    @Test func forgetAlwaysClearsAndRevokesWhenItCan() async throws {
        let (_, service) = setup()
        let store = InMemoryShortcutTokenStore()
        let linking = ShortcutLinking(service: service, store: store)
        _ = try await linking.activate(accountID: 4201)
        await linking.forget()
        #expect(!store.isLinked)
        #expect(try await service.shortcutLinkStatus().linked == false)

        // Offline: still cleared locally.
        let offline = DincrService(client: APIClient(baseURL: FixtureBackend.baseURL, tokens: FixtureTokens(), transport: ScriptedTransport([.failure(.notConnectedToInternet)]), backoff: { _ in }))
        let kept = InMemoryShortcutTokenStore(ShortcutCredential(token: "dsc_synthetic", accountID: 1))
        await ShortcutLinking(service: offline, store: kept).forget(timeout: .seconds(1))
        #expect(!kept.isLinked)
    }

    @Test func theIssuedTokenNeverPrints() throws {
        let issued = try APIClient.decoder.decode(ShortcutTokenIssued.self, from: Data(#"{"status":"ok","token":"dsc_secret","created_at":"2026-10-28T12:00:00Z"}"#.utf8))
        #expect(!String(describing: issued).contains("dsc_secret"))
        #expect(!"\(issued)".contains("dsc_secret"))
    }
}
