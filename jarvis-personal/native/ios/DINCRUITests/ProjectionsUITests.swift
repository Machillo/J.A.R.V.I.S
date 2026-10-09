import XCTest

/// UX-14 — Patrimonio → Proyecciones: a VIP with every input known sees the 1, 3, 6 and 12-month
/// points; a VIP with unknown inputs sees no figure, only what is missing and a link to the existing
/// screen that takes it. Hoy shows no projection. Android twin: `ProjectionsUiTest`. Fixture data only.
final class ProjectionsUITests: XCTestCase {
    private func launch(plan: String = "vip", scenario: String = "populated", tab: String? = nil) -> XCUIApplication {
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", scenario, "-DincrSkipLogin", "-DincrPlan", plan,
                         "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        if let tab { arguments += ["-DincrTab", tab] }
        app.launchArguments = arguments
        app.launch()
        return app
    }

    private func element(_ identifier: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any)[identifier].firstMatch
    }

    private func open(_ identifier: String, in app: XCUIApplication) {
        let target = element(identifier, in: app)
        XCTAssertTrue(target.waitForExistence(timeout: 10), "missing \(identifier)")
        if !target.isHittable { app.swipeUp() }
        target.tap()
    }

    private func openProjections(_ app: XCUIApplication) {
        XCTAssertTrue(app.tabBars.buttons["Patrimonio"].waitForExistence(timeout: 10))
        app.tabBars.buttons["Patrimonio"].tap()
        open("wealth.projections", in: app)
        XCTAssertTrue(app.navigationBars["Proyecciones"].waitForExistence(timeout: 10))
    }

    func testVipWithKnownInputsSeesTheFourHorizons() {
        let app = launch()
        openProjections(app)
        for months in [1, 3, 6, 12] {
            let point = element("projections.point.\(months)", in: app)
            if !point.waitForExistence(timeout: 5) { app.swipeUp() }
            XCTAssertTrue(point.waitForExistence(timeout: 5), "\(months)")
        }
        XCTAssertFalse(element("projections.incomplete", in: app).exists)
        XCTAssertFalse(element("projections.lowConfidence", in: app).exists)
    }

    func testIncompleteProjectionShowsNoFigureAndLinksToTheExistingScreens() {
        let app = launch(scenario: "empty")
        openProjections(app)
        XCTAssertTrue(element("projections.incomplete", in: app).waitForExistence(timeout: 10))
        for months in [1, 3, 6, 12] { XCTAssertFalse(element("projections.point.\(months)", in: app).exists, "\(months)") }
        XCTAssertFalse(app.staticTexts["Patrimonio neto"].exists)  // no figure from an unknown
        for (code, title) in [("income", "Ingresos y base"), ("essential_expenses", "Ingresos y base"), ("savings", "Tus ahorros")] {
            open("projections.missing.\(code)", in: app)
            XCTAssertTrue(app.navigationBars[title].waitForExistence(timeout: 10), code)
            app.navigationBars.buttons.element(boundBy: 0).tap()
            XCTAssertTrue(app.navigationBars["Proyecciones"].waitForExistence(timeout: 10))
        }
        XCTAssertFalse(element("projections.missing.debt_payments", in: app).exists)  // the account has no debt
    }

    func testHoyShowsNoProjection() {
        for scenario in ["populated", "empty"] {
            let app = launch(scenario: scenario)
            XCTAssertTrue(app.tabBars.buttons["Hoy"].waitForExistence(timeout: 10))
            XCTAssertTrue(element("home.debts", in: app).waitForExistence(timeout: 10), scenario)  // Hoy has loaded
            XCTAssertEqual(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS[c] 'proyecci'")).count, 0, scenario)
            app.terminate()
        }
    }

    // UX-14 / I09 — the charts.

    func testACompleteProjectionShowsTheChartsAndKeepsTheCards() {
        for role in [nil, "owner"] as [String?] {
            let app = launch()
            if role == nil { openProjections(app) } else {
                app.terminate()
                let owner = XCUIApplication()
                owner.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrPlan", "vip",
                                         "-DincrRole", "owner", "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
                owner.launch()
                openProjections(owner)
                assertCharts(owner, context: "owner")
                owner.terminate()
                continue
            }
            assertCharts(app, context: "vip")
            app.terminate()
        }
    }

    private func assertCharts(_ app: XCUIApplication, context: String) {
        for kind in ["cash", "debt", "netWorth"] {
            XCTAssertTrue(element("projections.chart.\(kind)", in: app).waitForExistence(timeout: 10), "\(context): \(kind)")
        }
        // VoiceOver: the chart says its title and every point.
        let cash = app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", "Efectivo proyectado")).firstMatch
        XCTAssertTrue(cash.exists, context)
        let spoken = (cash.value as? String) ?? ""
        for months in ["1 mes", "3 meses", "6 meses", "12 meses"] { XCTAssertTrue(spoken.contains(months), "\(context): \(months) in \(spoken)") }
        // The cards stay as the text alternative.
        for months in [1, 3, 6, 12] {
            let card = element("projections.point.\(months)", in: app)
            for _ in 0..<4 where !card.exists { app.swipeUp() }
            XCTAssertTrue(card.exists, "\(context): card \(months)")
        }
    }

    func testAnIncompleteProjectionShowsNoChart() {
        let app = launch(scenario: "empty")
        openProjections(app)
        XCTAssertTrue(element("projections.incomplete", in: app).waitForExistence(timeout: 10))
        for kind in ["cash", "debt", "netWorth"] { XCTAssertFalse(element("projections.chart.\(kind)", in: app).exists, kind) }
    }

    func testFreeAndBasicKeepProjectionsLocked() {
        for plan in ["free", "basic"] {
            let app = launch(plan: plan, tab: "wealth")
            let row = element("wealth.projections", in: app)
            XCTAssertTrue(row.waitForExistence(timeout: 10), plan)
            XCTAssertTrue(row.label.contains("Disponible desde VIP"), plan)
            app.terminate()
        }
    }
}
