import Foundation
import Testing
@testable import DincrCore

/// Money input/format and contract cases from the C4 audit. The Kotlin twin is `AuditTest` in
/// android/core/data: both platforms must give the same answers.
@Suite struct AuditTests {
    // MARK: Amount input — nothing ambiguous is guessed

    static let dotComma: [(String, Decimal?)] = [
        ("1", 1), ("1.5", nil), ("1,5", Decimal(string: "1.5")!), ("1,000", nil), ("1.000", 1_000),
        ("1,000.50", nil), ("1.000,50", Decimal(string: "1000.5")!), ("₡1.000", nil), ("$1,000.50", nil),
        (" 18 450 ", 18_450), ("-5", nil), ("0", nil), ("0,00", nil), ("", nil), ("abc", nil), ("NaN", nil),
        ("Infinity", nil), ("1e5", nil), ("999.999.999.999,99", Decimal(string: "999999999999.99")!),
        ("1.000.000.000.000", nil), ("12,345", nil),
    ]
    static let commaDot: [(String, Decimal?)] = [
        ("1", 1), ("1.5", Decimal(string: "1.5")!), ("1,5", nil), ("1,000", 1_000), ("1.000", nil),
        ("1,000.50", Decimal(string: "1000.5")!), ("1.000,50", nil), ("₡1.000", nil), ("$1,000.50", nil),
        (" 18 450 ", 18_450), ("-5", nil), ("0", nil), ("0.00", nil), ("", nil), ("abc", nil), ("NaN", nil),
        ("Infinity", nil), ("1e5", nil), ("999,999,999,999.99", Decimal(string: "999999999999.99")!),
        ("1,000,000,000,000", nil), ("12.345", nil),
    ]

    @Test(arguments: dotComma)
    func dotCommaInput(text: String, expected: Decimal?) {
        #expect(AmountInput.parse(text, separators: .dotComma) == expected, "\(text)")
    }

    @Test(arguments: commaDot)
    func commaDotInput(text: String, expected: Decimal?) {
        #expect(AmountInput.parse(text, separators: .commaDot) == expected, "\(text)")
    }

    // MARK: Editing never rewrites a stored amount

    @Test(arguments: [
        (MoneyFormat(currency: "CRC", separators: .dotComma), Decimal(string: "18450.5")!, "18.450,5"),
        (MoneyFormat(currency: "CRC", separators: .commaDot), Decimal(string: "12345.5")!, "12,345.5"),
        (MoneyFormat(currency: "USD", separators: .commaDot), Decimal(string: "1234.56")!, "1,234.56"),
        (MoneyFormat(currency: "CRC", separators: .dotComma), Decimal(1_000_000), "1.000.000"),
        (MoneyFormat(currency: "USD", separators: .dotComma), Decimal(string: "999999999999.99")!, "999.999.999.999,99"),
    ])
    func inputTextRoundTripsExactly(format: MoneyFormat, amount: Decimal, text: String) {
        #expect(format.inputText(amount) == text)
        #expect(AmountInput.parse(format.inputText(amount), separators: format.separators) == amount)
    }

    // MARK: Display and spoken form

    @Test func displayRoundsHalfAwayFromZeroLikeTheWebApp() {
        let crc = MoneyFormat()
        #expect(crc.string(Decimal(string: "2.5")!) == "₡3")
        #expect(crc.string(Decimal(string: "1234.6")!) == "₡1.235")
        #expect(crc.string(Decimal(string: "-1234.5")!) == "−₡1.235")
        #expect(crc.string(0) == "₡0")
        #expect(MoneyFormat(currency: "USD", separators: .commaDot).string(Decimal(string: "1234.6")!) == "$1,234.60")
        #expect(MoneyFormat(currency: "USD", separators: .commaDot).string(Decimal(string: "-0.005")!) == "−$0.01")
        #expect(MoneyFormat(currency: "EUR", separators: .dotComma, placement: .after).string(Decimal(string: "1234.6")!) == "1.234,60 €")
        // Legacy base currencies keep their code, never converted and never shown as ₡ or $.
        #expect(MoneyFormat(currency: "ARS").string(Decimal(1_234)) == "ARS 1.234,00")
    }

    @Test func spokenAmountNamesTheCurrencyShown() {
        let crc = MoneyFormat()
        #expect(crc.spoken(Decimal(string: "1234.5")!, currency: "USD", language: .english) == "1234.5 dollars")
        #expect(crc.spoken(Decimal(string: "1234.5")!, language: .english) == "1235 colones")
        #expect(MoneyFormat(currency: "EUR").spoken(2, language: .spanish) == "2 euros")
    }

    // MARK: Contract

    @Test func decodesTheRealIdentityShape() throws {
        let url = try #require(Bundle.module.url(forResource: "me", withExtension: "json", subdirectory: "Fixtures"))
        let profile = try APIClient.decoder.decode(Profile.self, from: Data(contentsOf: url))
        #expect(profile.id == 4201, "allowed_users.id is an integer")
        #expect(profile.profileSetupCompleted == true && profile.planSelected == true)
    }

    @Test func missingGateFlagsStayUnknown() throws {
        let profile = try APIClient.decoder.decode(Profile.self, from: Data(#"{"id":1}"#.utf8))
        #expect(profile.profileSetupCompleted == nil && profile.planSelected == nil && profile.role == nil)
        #expect(!profile.isOwner)
    }

    @Test func moneyDecodesWithoutBinaryRounding() throws {
        let json = #"[{"movement_id":"expense:1","amount":999999999999.99,"transaction_type":"expense","editable":true},{"movement_id":"expense:2","amount":0.1,"transaction_type":"expense","editable":true}]"#
        let rows = try APIClient.decoder.decode([Movement].self, from: Data(json.utf8))
        #expect(rows[0].amount == Decimal(string: "999999999999.99"))
        #expect(rows[1].amount == Decimal(string: "0.1"))
    }

    @Test func rowsTypedInAnotherCurrencyAreReadOnlyHere() throws {
        let json = #"{"movement_id":"expense:1","amount":5200,"transaction_type":"expense","editable":true,"original_amount":10,"original_currency":"USD"}"#
        let row = try APIClient.decoder.decode(Movement.self, from: Data(json.utf8))
        #expect(row.isEditable(baseCurrency: "CRC") == false)
        #expect(row.isEditable(baseCurrency: "usd"))
        let plain = #"{"movement_id":"expense:2","amount":1,"transaction_type":"expense","editable":true}"#
        #expect(try APIClient.decoder.decode(Movement.self, from: Data(plain.utf8)).isEditable(baseCurrency: "CRC"))
    }

    @Test func dashboardIgnoresUnknownFields() throws {
        let json = #"{"month":"2026-09","income":1,"expenses":1,"categories":[],"monthly_history":[],"future_field":{"x":1}}"#
        #expect(try APIClient.decoder.decode(FreeDashboard.self, from: Data(json.utf8)).month == "2026-09")
    }

    @Test func errorDetailMayBeAListOrAnObject() {
        let list = APIError.from(status: 422, body: Data(#"{"detail":[{"loc":["body","amount"],"msg":"x"}]}"#.utf8), language: .spanish, requestID: nil)
        #expect(list.kind == .validation && list.message == "Revisá la información e intentá nuevamente.")
        let object = APIError.from(status: 409, body: Data(#"{"detail":{"code":"account_deletion_pending","message":"Tu cuenta se está eliminando."}}"#.utf8), language: .english, requestID: nil)
        #expect(object.code == "account_deletion_pending" && object.message == "Tu cuenta se está eliminando.")
        #expect(APIError.from(status: 402, body: Data(), language: .spanish, requestID: nil).kind == .subscriptionRequired)
        #expect(APIError.from(status: 503, body: Data(#"{"detail":"x","code":"feature_temporarily_unavailable"}"#.utf8), language: .spanish, requestID: nil).kind == .server)
    }

    // MARK: Writes

    @Test func createsCarryTheIdempotencyKeyAndAreNeverRetried() async throws {
        let transport = ScriptedTransport([.status(503, "{}"), .status(200, "{}")])
        let client = APIClient(baseURL: URL(string: "https://api.example.test")!, tokens: CountingTokens(), transport: transport, language: .spanish, backoff: { _ in })
        let entry = EntryCreate(amount: 1, description: "x", category: "Comida", entryDate: nil)
        await #expect(throws: APIError.self) { try await LiveDincrService(client: client).create(.expense, entry, idempotencyKey: "key-12345678") }
        #expect(transport.requests.count == 1)
        #expect(transport.requests[0].value(forHTTPHeaderField: "X-Idempotency-Key") == "key-12345678")
        #expect(transport.requests[0].url?.path == "/user-product/finance/expenses")
    }

    @Test func fixtureServiceMirrorsBackendWriteSemantics() async throws {
        let service = FixtureDincrService(scenario: .empty, latency: .zero)
        let entry = EntryCreate(amount: 1, description: "x", category: "Comida", entryDate: "2026-09-25")
        try await service.create(.expense, entry, idempotencyKey: "same-key-1")
        try await service.create(.expense, entry, idempotencyKey: "same-key-1")
        let rows = try await service.movements()
        #expect(rows.count == 1, "a replayed key must not add a second row")
        try await service.delete(movementID: rows[0].movementId)
        await #expect(throws: APIError.self) { try await service.delete(movementID: rows[0].movementId) }
    }

    @Test func cancelledRequestsAreNotReportedAsOffline() async {
        let transport = ScriptedTransport([.failure(.cancelled)])
        let client = APIClient(baseURL: URL(string: "https://api.example.test")!, tokens: CountingTokens(), transport: transport, language: .spanish, backoff: { _ in })
        await #expect(throws: CancellationError.self) { let _: Acknowledgement = try await client.get("/auth/me") }
    }

    // MARK: Search

    @Test func searchIgnoresCaseAndAccents() {
        #expect(SearchText.matches("credito", in: ["Pago de Crédito"]))
        #expect(SearchText.matches("  CAFÉ ", in: [nil, "cafe"]))
        #expect(SearchText.matches("", in: [nil]))
        #expect(!SearchText.matches("alquiler", in: ["Supermercado", nil]))
    }
}
