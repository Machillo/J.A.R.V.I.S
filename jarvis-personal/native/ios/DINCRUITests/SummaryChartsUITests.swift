import XCTest

/// E04 / E05 — Movimientos → Análisis → Resumen del mes draws the month's income vs expenses as bars
/// and its expenses by category as a donut, below the amounts (still there as text). VoiceOver reads
/// the bars' amounts and every category with its share. An empty month says so instead of drawing.
/// Every plan reaches the summary; only the Owner keeps the Owner analysis entry. Android twin:
/// `SummaryChartsUiTest`. Fixture data only.
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

    private var thisMonth: String {
        ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"][Calendar.current.component(.month, from: .now) - 1]
    }

    func testEveryPlanSeesTheBarsAndTheDonutWithTheAmountsKept() {
        for (plan, role) in [(nil, nil), ("basic", nil), ("vip", nil), ("vip", "owner")] as [(String?, String?)] {
            let context = role ?? plan ?? "free"
            let app = launch(plan: plan, role: role)
            open("movements.analysis", in: app)
            XCTAssertTrue(element("analysis.summary", in: app).waitForExistence(timeout: 10), context)
            XCTAssertEqual(element("analysis.owner", in: app).exists, role == "owner", "\(context): the Owner entry stays the Owner's")
            open("analysis.summary", in: app)

            // The amounts stay as text above the charts.
            XCTAssertTrue(text("Ingresos", in: app).waitForExistence(timeout: 10), context)
            XCTAssertTrue(text("Gastos", in: app).exists, context)

            let bars = reveal("summary.flow.chart", in: app)
            XCTAssertTrue(bars.waitForExistence(timeout: 10), "\(context): E04 bars")
            XCTAssertEqual(bars.label, "Ingresos y gastos de \(thisMonth)", "\(context): VoiceOver names the month")
            let spoken = bars.value as? String ?? ""
            XCTAssertNotNil(spoken.range(of: "^\\w+: Ingresos [0-9]+ colones, Gastos [0-9]+ colones$", options: .regularExpression),
                            "\(context): VoiceOver reads both amounts (\(spoken))")

            XCTAssertTrue(reveal("summary.categories", in: app).waitForExistence(timeout: 10), "\(context): E05 donut")
            let part = app.descendants(matching: .any).matching(NSPredicate(format: "label MATCHES %@", "^Comida: [0-9]+ colones, [0-9]+ %$")).firstMatch
            XCTAssertTrue(part.waitForExistence(timeout: 10), "\(context): VoiceOver reads each category with its amount and share")
            XCTAssertFalse(text("Todavía no hay datos", in: app).exists, context)
            app.terminate()
        }
    }

    func testAMonthWithNothingRecordedSaysSoInsteadOfDrawing() {
        let app = launch(scenario: "empty")
        openSummary(app)
        let notice = element("summary.flow.notice", in: app)
        XCTAssertTrue(notice.waitForExistence(timeout: 10))
        XCTAssertEqual(notice.label, "Todavía no hay ingresos ni gastos registrados en este mes.")
        XCTAssertFalse(element("summary.flow.chart", in: app).exists, "no bars of nothing")
        _ = reveal("summary.categories", in: app)
        XCTAssertTrue(text("Gastos por categoría. Todavía no hay datos.", in: app).waitForExistence(timeout: 10), "the donut says why it isn't drawn")
    }

    func testAPreviousMonthDrawsItsOwnSummary() {
        let app = launch()
        openSummary(app)
        XCTAssertTrue(element("summary.flow.chart", in: app).waitForExistence(timeout: 10))
        let previous = app.buttons["Mes anterior"]
        XCTAssertTrue(previous.waitForExistence(timeout: 10))
        for _ in 0..<12 { previous.tap() }
        // A year back the fixture has nothing recorded: the bars give way to the notice.
        XCTAssertTrue(element("summary.flow.notice", in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(element("summary.flow.chart", in: app).exists)
    }
}
