import Foundation
import Testing
@testable import DincrCore

/// K-2: the monthly review never shows the financial-health score (no canonical calculation until
/// P3.7); every other scorecard line stays as the backend sends it. Android: `PublicScorecardTest.kt`.
/// Synthetic data.
@Suite struct PublicScorecardTests {
    private func review(_ json: String) throws -> MonthlyReview {
        try APIClient.decoder.decode(MonthlyReview.self, from: Data(json.utf8))
    }

    @Test func theHealthScoreLineIsLeftOutAndTheRestKeptInOrder() throws {
        let review = try review(#"""
        {"status":"OK","scorecard":[{"key":"debt_total","label":"Deuda total","unit":"CRC","current":810000,"trend":"improved"},
          {"key":"health_score","label":"Salud financiera","unit":"points","current":72,"baseline":66,"delta":6,"trend":"improved"},
          {"key":"net_operational","label":"Flujo operativo","unit":"CRC","current":180000,"trend":"declined"}]}
        """#)
        #expect(review.publicScorecard.map(\.key) == ["debt_total", "net_operational"])
        #expect(review.publicScorecard.allSatisfy { $0.unit != "points" })
    }

    @Test func anIncompleteHealthLineIsLeftOutToo() throws {
        let review = try review(#"{"scorecard":[{"key":"health_score","label":"Salud financiera","unit":"points","trend":"unknown","explanation":"Falta la tasa"}]}"#)
        #expect(review.publicScorecard.isEmpty)
    }

    @Test func aReviewWithoutScorecardHasNoLines() throws {
        #expect(try review(#"{"status":"BASELINE"}"#).publicScorecard.isEmpty)
    }

    @Test func theFixtureSendsTheHealthLineAndTheAppDropsIt() async throws {
        let review = try await FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero)).monthlyReview(period: "2026-10")
        #expect(review.scorecard?.contains { $0.key == MonthlyReview.healthScoreKey } == true)
        #expect(review.publicScorecard.map(\.key) == ["debt_total", "emergency_coverage_months", "net_operational"])
    }
}
