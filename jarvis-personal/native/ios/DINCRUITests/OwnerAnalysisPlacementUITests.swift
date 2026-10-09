import XCTest

/// §15 PR 11 — the Owner's historical financial analysis in Movimientos → Análisis, in its Análisis
/// mode: income and expenses, spending by category, month end and recommendations, with no health score
/// (P3.7) and no net worth (P0.9). Free, Basic and VIP never see the entry. JARVIS → Análisis financiero
/// keeps every section. Android twin: `OwnerAnalysisPlacementUiTest`. Fixture data only.
final class OwnerAnalysisPlacementUITests: XCTestCase {
    private func launch(plan: String? = nil, role: String? = nil, tab: String) -> XCUIApplication {
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrTab", tab,
                         "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        if let plan { arguments += ["-DincrPlan", plan] }
        if let role { arguments += ["-DincrRole", role] }
        app.launchArguments = arguments
        app.launch()
        return app
    }

    private func element(_ id: String, in app: XCUIApplication) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }

    private func open(_ id: String, in app: XCUIApplication) {
        let target = element(id, in: app)
        XCTAssertTrue(target.waitForExistence(timeout: 10), "missing \(id)")
        if !target.isHittable { app.swipeUp() }
        target.tap()
    }

    private func contains(_ text: String, in app: XCUIApplication) -> Bool {
        app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", text)).count > 0
    }

    /// Scrolls down until `id` exists (the screen is long), at most a few times.
    private func reveal(_ id: String, in app: XCUIApplication) -> Bool {
        for _ in 0..<6 {
            if element(id, in: app).exists { return true }
            app.swipeUp()
        }
        return element(id, in: app).exists
    }

    func testFreeBasicAndVipNeverSeeTheOwnerEntry() {
        for plan in [nil, "basic", "vip"] as [String?] {
            let app = launch(plan: plan, tab: "movements")
            open("movements.analysis", in: app)
            XCTAssertTrue(element("analysis.summary", in: app).waitForExistence(timeout: 10), plan ?? "free")
            XCTAssertFalse(element("analysis.owner", in: app).exists, plan ?? "free")
            app.terminate()
        }
    }

    func testTheOwnerSeesTheAnalysisModeWithoutScoreOrNetWorth() {
        let app = launch(plan: "vip", role: "owner", tab: "movements")
        open("movements.analysis", in: app)
        open("analysis.owner", in: app)
        XCTAssertTrue(app.navigationBars["Análisis financiero"].waitForExistence(timeout: 10))
        XCTAssertTrue(element("jarvis.analysis.flow", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(reveal("jarvis.analysis.spending", in: app))
        XCTAssertTrue(reveal("jarvis.analysis.monthEnd", in: app))
        for hidden in ["jarvis.analysis.health", "jarvis.analysis.networth"] { XCTAssertFalse(element(hidden, in: app).exists, hidden) }
        for hidden in ["/100", "Salud financiera"] { XCTAssertFalse(contains(hidden, in: app), hidden) }
        XCTAssertEqual(app.tabBars.buttons.allElementsBoundByIndex.map { $0.label }, ["Hoy", "Movimientos", "Plan", "Patrimonio", "Perfil"])
    }

    func testJarvisKeepsTheFullAnalysis() {
        let app = launch(plan: "vip", role: "owner", tab: "profile")
        open("profile.jarvis", in: app)
        open("jarvis.section.analysis", in: app)
        XCTAssertTrue(element("jarvis.analysis.health", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(contains("/100", in: app))
        XCTAssertTrue(reveal("jarvis.analysis.networth", in: app))
    }
}
