import Foundation
import Testing
@testable import DincrCore

/// "Para atender" (UX-5): presentation rules only, synthetic data. Android: `AttentionListTest.kt`.
@Suite struct AttentionTests {
    private func center(_ json: String) throws -> CommandCenter {
        try APIClient.decoder.decode(CommandCenter.self, from: Data(json.utf8))
    }

    private func advisor(_ json: String) throws -> ProactiveAdvisor {
        try APIClient.decoder.decode(ProactiveAdvisor.self, from: Data(json.utf8))
    }

    private func alerts(_ severities: [String]) -> String {
        severities.enumerated().map { #"{"severity":"\#($1)","title":"A\#($0)","context":"c\#($0)","action":"Hacé algo"}"# }.joined(separator: ",")
    }

    // MARK: 0 / 1 / 3 / >3

    @Test func nothingToAttendLeavesTheSectionOut() throws {
        #expect(AttentionList.today(center: nil).isEmpty)
        #expect(try AttentionList.today(center: center(#"{}"#)).isEmpty)
        #expect(try AttentionList.today(center: center(#"{"alerts":[],"automation":{"review":0}}"#)).isEmpty)
        // A title-less alert says nothing: it is not shown.
        #expect(try AttentionList.today(center: center(#"{"alerts":[{"severity":"high","title":"  "}]}"#)).isEmpty)
    }

    @Test func oneItemIsShownWithoutSeeAll() throws {
        let today = AttentionList.today(center: try center(#"{"alerts":[\#(alerts(["medium"]))]}"#))
        #expect(today.visible.count == 1 && !today.showsSeeAll)
    }

    @Test func exactlyThreeAreShownWithoutSeeAll() throws {
        let today = AttentionList.today(center: try center(#"{"alerts":[\#(alerts(["medium", "high", "medium"]))]}"#))
        #expect(today.visible.count == 3 && !today.showsSeeAll)
    }

    @Test func moreThanThreeShowThreeAndSeeAll() throws {
        let value = try center(#"{"alerts":[\#(alerts(["medium", "medium", "high", "critical"]))],"automation":{"review":2}}"#)
        let today = AttentionList.today(center: value)
        #expect(today.visible.count == 3 && today.showsSeeAll)
        // The full list is the same items, uncapped.
        #expect(AttentionList.items(center: value, advisor: nil).count == 5)
        #expect(Array(AttentionList.items(center: value, advisor: nil).prefix(3)) == today.visible)
    }

    // MARK: Order

    @Test func criticalThenHighThenMediumThenSuccess() throws {
        let value = try center(#"{"alerts":[\#(alerts(["medium", "high", "critical"]))]}"#)
        let advice = try advisor(#"{"status":"ALERTS","alerts":[{"id":"p","code":"debt_progress","severity":"success","title":"Tu deuda disminuyó","explanation":"e","action":{"label":"Ver","route":"vip-monthly-review"}},{"id":"h","code":"debt_increase","severity":"high","title":"Subió la deuda","explanation":"e","action":{"route":"debts"}}]}"#)
        let items = AttentionList.items(center: value, advisor: advice)
        #expect(items.map(\.severity) == ["critical", "high", "high", "medium", "success"])
        // Same severity: command center before the advisor.
        #expect(items[1].source == .commandCenter && items[2].source == .advisor)
        #expect(items.last?.kind == .positive)
    }

    @Test func theOwnersCriticalComesBeforeHigh() throws {
        // Was: only "high" was urgent, so a critical alert came after the high ones.
        let items = AttentionList.today(center: try center(#"{"alerts":[\#(alerts(["high", "critical"]))]}"#)).visible
        #expect(items.map(\.severity) == ["critical", "high"])
    }

    @Test func theOrderIsDeterministicAndKeepsTheBackendsOrderWithinASeverity() throws {
        let value = try center(#"{"alerts":[\#(alerts(["medium", "medium", "medium"]))]}"#)
        let first = AttentionList.items(center: value, advisor: nil)
        #expect(first.map(\.title) == ["A0", "A1", "A2"])
        #expect(first == AttentionList.items(center: value, advisor: nil))
    }

    @Test func anUnknownSeverityIsNeverDowngraded() {
        #expect(AttentionList.rank("critical") < AttentionList.rank("high"))
        #expect(AttentionList.rank("high") < AttentionList.rank("medium"))
        #expect(AttentionList.rank("unexpected") == AttentionList.rank("medium"))
        #expect(AttentionList.rank(nil) < AttentionList.rank("success"))
    }

    // MARK: Semantics (UX-1)

    @Test func financialMattersAreAttentionNeverTechnicalErrors() throws {
        let value = try center(#"{"alerts":[\#(alerts(["critical", "high", "medium"]))],"automation":{"review":1}}"#)
        let items = AttentionList.items(center: value, advisor: nil)
        #expect(items.allSatisfy { $0.kind == .attention })
        #expect(!items.contains { $0.kind == .technicalError })
    }

    @Test func successIsPositiveAndARecommendationIsAnOpportunity() throws {
        let advice = try advisor(#"{"status":"ALERTS","alerts":[{"id":"s","code":"strategy_changed","severity":"medium","title":"DINCR reajustó tu estrategia","explanation":"La prioridad cambió.","action":{"route":"strategy"}},{"id":"m","code":"emergency_milestone_1","severity":"success","title":"Alcanzaste un hito","explanation":"1 mes","action":{"route":"vip-emergency"}}]}"#)
        let items = AttentionList.items(center: nil, advisor: advice)
        #expect(items.first { $0.title.hasPrefix("DINCR") }?.kind == .opportunity)
        #expect(items.first { $0.title.hasPrefix("Alcanzaste") }?.kind == .positive)
        #expect(items.allSatisfy { $0.isChange })   // the advisor reports changes, not the absolute state
    }

    // MARK: Sources and duplicates

    @Test func theAdvisorIsNeverInTodaysThreeButIsInTheFullList() throws {
        let value = try center(#"{"alerts":[\#(alerts(["medium"]))]}"#)
        let advice = try advisor(#"{"status":"ALERTS","alerts":[{"id":"x","code":"debt_increase","severity":"critical","title":"Subió la deuda","explanation":"e","action":{"route":"debts"}}]}"#)
        #expect(!AttentionList.today(center: value).visible.contains { $0.source == .advisor })
        #expect(AttentionList.items(center: value, advisor: advice).first?.source == .advisor)
    }

    @Test func pendingNoticesAndTheirAlertAreOneItem() throws {
        let value = try center(#"""
        {"alerts":[{"severity":"medium","title":"Movimientos por revisar","context":"Hay 3 movimientos importados sin confirmar.","action":"Revisalos antes de confiar en el cierre mensual."}],
         "automation":{"review":3}}
        """#)
        let items = AttentionList.items(center: value, advisor: nil)
        #expect(items.count == 1)
        #expect(items[0].source == .review && items[0].destination == .review)
        #expect(items[0].message.hasPrefix("Hay 3 movimientos"))   // the command center's own words
        // In English the same alert is merged too.
        let english = try center(#"{"alerts":[{"severity":"medium","title":"Transactions to review","context":"c"}],"automation":{"review":1}}"#)
        #expect(AttentionList.items(center: english, advisor: nil, language: .english).count == 1)
    }

    @Test func pendingNoticesWithoutTheirAlertStillGetOneItem() throws {
        let items = AttentionList.items(center: try center(#"{"automation":{"review":2}}"#), advisor: nil, language: .spanish)
        #expect(items.count == 1 && items[0].destination == .review && items[0].message.contains("2 avisos"))
    }

    @Test func noPendingNoticesMeansNoReviewItem() throws {
        let items = AttentionList.items(center: try center(#"{"alerts":[{"severity":"medium","title":"Movimientos por revisar","context":"c"}],"automation":{"review":0}}"#), advisor: nil)
        #expect(items.count == 1 && items[0].destination == nil && items[0].source == .commandCenter)
    }

    @Test func theHealthScoreIsNotAFactInTheList() throws {
        let advice = try advisor(#"{"status":"ALERTS","alerts":[{"id":"h","code":"health_score_drop","severity":"high","title":"Bajó tu salud financiera","explanation":"−12 puntos","action":{"route":"situation"}}]}"#)
        #expect(AttentionList.items(center: nil, advisor: advice).isEmpty)
    }

    @Test func pausedMailAutomationKeepsTheNoticesWithoutALink() throws {
        let value = try center(#"{"alerts":[{"severity":"medium","title":"Movimientos por revisar","context":"c"}],"automation":{"review":3}}"#)
        let items = AttentionList.items(center: value, advisor: nil, mailReviewAvailable: false)
        #expect(items.count == 1 && items[0].source == .review && items[0].destination == nil)
        #expect(try AttentionList.today(center: center(#"{"automation":{"review":1}}"#), mailReviewAvailable: false).visible.first?.destination == nil)
    }

    @Test func anUnavailableSourceIsNotATechnicalProblem() {
        #expect(AttentionList.isUnavailable(APIError(kind: .featureUnavailable, status: 503, message: "x")))
        #expect(AttentionList.isUnavailable(APIError(kind: .forbidden, status: 403, message: "x")))
        #expect(AttentionList.isUnavailable(APIError(kind: .subscriptionRequired, status: 402, message: "x")))
        #expect(!AttentionList.isUnavailable(APIError(kind: .server, status: 500, message: "x")))
        #expect(!AttentionList.isUnavailable(APIError(kind: .offline, message: "x")))
        #expect(!AttentionList.isUnavailable(CancellationError()))
    }

    // MARK: Destinations

    @Test func commandCenterFreeTextNeverBecomesALink() throws {
        let items = AttentionList.items(center: try center(#"{"alerts":[{"severity":"high","title":"Saldo bajo","context":"c","action":"Revisá la deuda"}]}"#), advisor: nil)
        #expect(items[0].destination == nil)
        #expect(items[0].message == "c Revisá la deuda")   // kept as words
    }

    @Test func advisorRoutesOpenTheirRealScreens() {
        #expect(AttentionList.destination(advisorRoute: "debts") == .debts)
        #expect(AttentionList.destination(advisorRoute: "vip-emergency") == .salvavidas)
        #expect(AttentionList.destination(advisorRoute: "situation") == .incomeBase)  // UX-7: no Situación screen
        #expect(AttentionList.destination(advisorRoute: "strategy") == .strategy)
        #expect(AttentionList.destination(advisorRoute: "finance") == .movements)
        #expect(AttentionList.destination(advisorRoute: "/vip-monthly-review") == .monthlyReview)
    }

    @Test func anUnknownAdvisorRouteIsShownWithoutALink() throws {
        #expect(AttentionList.destination(advisorRoute: "vip-projections") == nil)
        #expect(AttentionList.destination(advisorRoute: nil) == nil)
        let advice = try advisor(#"{"status":"ALERTS","alerts":[{"id":"u","code":"new_code","severity":"medium","title":"Algo nuevo","explanation":"e","action":{"route":"somewhere"}}]}"#)
        let items = AttentionList.items(center: nil, advisor: advice)
        #expect(items.count == 1 && items[0].destination == nil)
    }

    // MARK: Data

    @Test func noAmountIsInventedAndTheBackendWordsAreKept() throws {
        // The list never computes or rewrites figures: messages are the backend's text as sent.
        let value = try center(#"{"alerts":[{"severity":"critical","title":"Cierre mensual negativo","context":"Faltan ₡150,000 para cubrir compromisos conocidos.","action":null}]}"#)
        let items = AttentionList.items(center: value, advisor: nil)
        #expect(items[0].message == "Faltan ₡150,000 para cubrir compromisos conocidos.")
        // With no alerts (for example an unknown income, #324) nothing is shown: no zero is made up.
        #expect(try AttentionList.items(center: center(#"{"alerts":[],"safe_to_spend":{"amount":0}}"#), advisor: nil).isEmpty)
    }
}
