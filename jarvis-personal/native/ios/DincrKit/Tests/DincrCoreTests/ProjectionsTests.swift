import Foundation
import Testing
@testable import DincrCore

/// UX-14 (UNKNOWN ≠ 0): Patrimonio → Proyecciones shows figures only when the command center says
/// the projection is complete; otherwise it names what is missing and where to give it. Hoy gets no
/// projection item. Android: `ProjectionsTest.kt`. Synthetic data.
@Suite struct ProjectionsTests {
    private func center(_ json: String) throws -> CommandCenter {
        try APIClient.decoder.decode(CommandCenter.self, from: Data(json.utf8))
    }

    private let complete = #"""
    {"projections":[{"months":12,"cash":6900000,"debt":0,"net_worth":6900000,"confidence":"medium"},
                    {"months":1,"cash":850000,"debt":450000,"net_worth":400000,"confidence":"medium"},
                    {"months":3,"cash":1950000,"debt":350000,"net_worth":1600000,"confidence":"medium"},
                    {"months":6,"cash":3600000,"debt":200000,"net_worth":3400000,"confidence":"medium"}],
     "projection_status":{"complete":true,"missing":[]},"alerts":[]}
    """#

    @Test func aCompleteProjectionKeepsTheFourHorizonsInOrder() throws {
        guard case .complete(let points, let low) = Projections.state(try center(complete)) else { Issue.record("not complete"); return }
        #expect(points.map(\.months) == [1, 3, 6, 12])
        #expect(points.first?.cash == Decimal(850000))
        #expect(low == false)
    }

    @Test func lowConfidenceIsSaidTheSameWayOnBothPlatforms() throws {
        let json = complete.replacingOccurrences(of: #""confidence":"medium""#, with: #""confidence":"low""#)
        guard case .complete(_, let low) = Projections.state(try center(json)) else { Issue.record("not complete"); return }
        #expect(low)
    }

    @Test func anIncompleteProjectionHasNoFigureAndNamesEveryMissingInput() throws {
        let state = Projections.state(try center(#"""
        {"projections":[],"projection_status":{"complete":false,"missing":["income","essential_expenses","debt_payments","savings"]}}
        """#))
        #expect(state == .incomplete(missing: [.income, .essentialExpenses, .debtPayments, .savings]))
    }

    @Test(arguments: [("income", ProjectionInput.income), ("essential_expenses", .essentialExpenses), ("debt_payments", .debtPayments), ("savings", .savings)])
    func eachUnknownInputAloneBlocksTheProjection(code: String, input: ProjectionInput) throws {
        let state = Projections.state(try center(#"{"projections":[],"projection_status":{"complete":false,"missing":["\#(code)"]}}"#))
        #expect(state == .incomplete(missing: [input]))
    }

    @Test func eachInputOpensTheExistingScreenThatTakesIt() {
        #expect(ProjectionInput.income.destination == .incomeBase)
        #expect(ProjectionInput.essentialExpenses.destination == .incomeBase)
        #expect(ProjectionInput.savings.destination == .declaredSavings)
        #expect(ProjectionInput.debtPayments.destination == .debts)
    }

    @Test func anAnswerWithoutStatusOrPointsIsNeverReadAsComplete() throws {
        // A backend without `projection_status`: its points are not trusted as complete.
        let old = try center(#"{"projections":[{"months":1,"cash":0,"debt":0,"net_worth":0,"confidence":"low"}]}"#)
        #expect(Projections.state(old) == .incomplete(missing: []))
        // Complete but no points: nothing to show as a figure.
        #expect(Projections.state(try center(#"{"projections":[],"projection_status":{"complete":true,"missing":[]}}"#)) == .incomplete(missing: []))
        // Codes this app doesn't know are skipped, never guessed.
        #expect(Projections.state(try center(#"{"projection_status":{"complete":false,"missing":["future_code","savings"]}}"#)) == .incomplete(missing: [.savings]))
    }

    @Test func hoyGetsNoProjectionItem() throws {
        // UX-14 D: no "material change" yet, so the projections never reach Para atender.
        #expect(AttentionList.today(center: try center(complete)).isEmpty)
        let incomplete = try center(#"{"projections":[],"projection_status":{"complete":false,"missing":["savings"]},"alerts":[]}"#)
        #expect(AttentionList.today(center: incomplete).isEmpty)
    }

    @Test func theFixtureMatchesTheContract() async throws {
        let populated = try await FixtureBackend.service(FixtureBackend(scenario: .populated, plan: .vip, latency: .zero)).commandCenter()
        guard case .complete(let points, _) = Projections.state(populated) else { Issue.record("populated not complete"); return }
        #expect(points.map(\.months) == [1, 3, 6, 12])
        let empty = try await FixtureBackend.service(FixtureBackend(scenario: .empty, plan: .vip, latency: .zero)).commandCenter()
        #expect(Projections.state(empty) == .incomplete(missing: [.income, .essentialExpenses, .savings]))
        #expect(empty.debtPlanner?.recommended == nil)
    }
}
