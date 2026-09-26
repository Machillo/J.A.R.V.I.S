import Foundation
import Testing
@testable import DincrCore

/// Pins the JSON contract of the endpoints the app decodes (OpenAPI has no response schemas yet;
/// see docs/native/CURRENT_STATE_AUDIT.md §6). Fixtures follow the backend serialization.
@Suite struct ContractTests {
    func fixture(_ name: String) throws -> Data {
        let url = try #require(Bundle.module.url(forResource: name, withExtension: "json", subdirectory: "Fixtures"))
        return try Data(contentsOf: url)
    }

    @Test func decodesFreeDashboardAndIgnoresUnknownFields() throws {
        let dashboard = try APIClient.decoder.decode(FreeDashboard.self, from: fixture("free_dashboard"))
        #expect(dashboard.month == "2026-09")
        #expect(dashboard.available == Decimal(string: "257549.5"))
        #expect(dashboard.categories.count == 2)
        #expect(dashboard.monthlyHistory.last?.expenses == Decimal(string: "512450.5"))
    }

    @Test func availablePrefersBackendFigureAndNeverInventsOne() throws {
        let noFigure = #"{"month":"2026-09","income":1,"expenses":1,"categories":[],"monthly_history":[]}"#
        let dashboard = try APIClient.decoder.decode(FreeDashboard.self, from: Data(noFigure.utf8))
        #expect(dashboard.available == nil, "unknown must stay unknown, not zero")
    }

    @Test func decodesMovementsIncludingReadOnlyAndDebtPayments() throws {
        let rows = try APIClient.decoder.decode([Movement].self, from: fixture("free_movements"))
        #expect(rows.count == 3)
        #expect(rows[0].transactionType == .income)
        #expect(rows[0].editable)
        #expect(rows[1].editable == false)
        #expect(rows[2].transactionType == .expense, "debt payments are money leaving")
        #expect(rows[2].day == nil)
    }

    @Test func decodesProfileFormattingPreferences() throws {
        let profile = try APIClient.decoder.decode(Profile.self, from: fixture("me"))
        #expect(profile.plan == "basic")
        #expect(profile.isOwner == false)
        #expect(profile.firstName == "Ana")
        let format = MoneyFormat(profile: profile)
        #expect(format.currency == "USD")
        #expect(format.separators == .commaDot)
        #expect(format.placement == .after)
    }

    @Test func ownerSessionsAreRecognized() throws {
        for role in ["owner", "admin"] {
            let json = #"{"id":"x","role":"\#(role)"}"#
            #expect(try APIClient.decoder.decode(Profile.self, from: Data(json.utf8)).isOwner)
        }
    }

    @Test func encodesRequestBodiesInSnakeCase() throws {
        let body = EntryCreate(amount: Decimal(string: "18450.5")!, description: "Súper", category: "Comida", entryDate: "2026-09-25")
        let json = try #require(String(data: APIClient.encoder.encode(body), encoding: .utf8))
        #expect(json.contains(#""entry_date":"2026-09-25""#))
        #expect(json.contains(#""amount":18450.5"#))
        let update = MovementUpdate(transactionDate: "2026-09-25", description: "x", amount: 1, transactionType: .expense, category: "Comida")
        let updateJSON = try #require(String(data: APIClient.encoder.encode(update), encoding: .utf8))
        #expect(updateJSON.contains(#""transaction_type":"expense""#))
        #expect(updateJSON.contains(#""transaction_date":"2026-09-25""#))
    }

    @Test func movementIDKeepsItsColonInThePath() {
        #expect(LiveDincrService.encode("expense:42") == "expense:42")
        #expect(LiveDincrService.encode("a/b") == "a%2Fb")
    }
}
