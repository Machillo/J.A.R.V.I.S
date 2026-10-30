import XCTest

/// Movimientos → Análisis → Resumen (simple): a month or a year, income, spending and what was saved
/// as text, and two donuts (where the money came from, where it went) that VoiceOver reads part by
/// part. An empty period says so. Every plan reaches it. Android twin: `SummaryChartsUiTest`.
/// Fixture data only.
final class SummaryChartsUITests: XCTestCase {
    private func launch(scenario: String = "populated", plan: String? = nil, role: String? = nil) -> XCUIApplication {
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", scenario, "-DincrSkipLogin", "-DincrTab", "movements",
                         "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        if let plan { arguments += ["-DincrPlan", plan] }
        if let role { arguments += ["-DincrRole", role] }
        app.launchArguments = arguments
        app.launch()
        return app
    }

    private func element(_ id: String, in app: XCUIApplication) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }

    private func text(_ content: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", content)).firstMatch
    }

    private func open(_ id: String, in app: XCUIApplication) {
        let target = element(id, in: app)
        XCTAssertTrue(target.waitForExistence(timeout: 10), "missing \(id)")
        if !target.isHittable { app.swipeUp() }
        target.tap()
    }

    /// Scrolls down until `id` exists (the screen is long), at most a few times.
    private func reveal(_ id: String, in app: XCUIApplication) -> XCUIElement {
        let target = element(id, in: app)
        for _ in 0..<6 where !(target.exists && target.isHittable) { app.swipeUp() }
        return target
    }

    private func openSummary(_ app: XCUIApplication) {
        open("movements.analysis", in: app)
        open("analysis.summary", in: app)
        XCTAssertTrue(app.navigationBars["Resumen del mes"].waitForExistence(timeout: 10))
    }

    func testEveryPlanSeesTheTotalsAndBothDonuts() {
        for (plan, role) in [(nil, nil), ("basic", nil), ("vip", nil), ("vip", "owner")] as [(String?, String?)] {
            let context = role ?? plan ?? "free"
            let app = launch(plan: plan, role: role)
            open("movements.analysis", in: app)
            XCTAssertTrue(element("analysis.summary", in: app).waitForExistence(timeout: 10), context)
            open("analysis.summary", in: app)

            XCTAssertTrue(element("summary.income", in: app).waitForExistence(timeout: 10), context)
            XCTAssertTrue(element("summary.expenses", in: app).exists, context)
            XCTAssertTrue(element("summary.saved", in: app).exists, "\(context): what was saved")
            XCTAssertTrue(reveal("summary.incomeSources", in: app).waitForExistence(timeout: 10), "\(context): where it came from")
            XCTAssertTrue(reveal("summary.categories", in: app).waitForExistence(timeout: 10), "\(context): where it went")
            let part = app.descendants(matching: .any).matching(NSPredicate(format: "label MATCHES %@", "^Comida: [0-9]+ colones, [0-9]+ %$")).firstMatch
            XCTAssertTrue(part.waitForExistence(timeout: 10), "\(context): VoiceOver reads each part with its amount and share")
            XCTAssertFalse(element("summary.flow.chart", in: app).exists, "\(context): no bars any more")
            app.terminate()
        }
    }

    func testAMonthWithNothingRecordedSaysSo() {
        let app = launch(scenario: "empty")
        openSummary(app)
        let notice = element("summary.flow.notice", in: app)
        XCTAssertTrue(notice.waitForExistence(timeout: 10))
        XCTAssertEqual(notice.label, "Todavía no hay ingresos ni gastos registrados en este mes.")
    }

    func testTheYearHasItsOwnSummary() {
        let app = launch()
        openSummary(app)
        app.segmentedControls["summary.scope"].buttons["Año"].tap()
        XCTAssertTrue(app.buttons["Año anterior"].waitForExistence(timeout: 10))
        XCTAssertTrue(element("summary.income", in: app).waitForExistence(timeout: 10))
        // Two years back the fixture has nothing recorded.
        app.buttons["Año anterior"].tap(); app.buttons["Año anterior"].tap()
        XCTAssertTrue(element("summary.flow.notice", in: app).waitForExistence(timeout: 10))
    }
}
