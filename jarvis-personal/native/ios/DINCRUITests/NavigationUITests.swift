import XCTest

/// UX-13 — the public navigation is exactly Hoy · Movimientos · Plan · Patrimonio · Perfil, and every
/// function of the retired DINCR tab is reached from its new home: Movimientos → Análisis (summary,
/// reports, monthly review), Patrimonio (projections, scenarios) and Hoy → Para atender (DINCR hoy).
/// Android twin: `NavigationUiTest`. Fixture data only.
final class NavigationUITests: XCTestCase {
    private static let tabs = ["Hoy", "Movimientos", "Plan", "Patrimonio", "Perfil"]

    private func launch(plan: String? = nil, role: String? = nil, tab: String? = nil) -> XCUIApplication {
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        if let plan { arguments += ["-DincrPlan", plan] }
        if let role { arguments += ["-DincrRole", role] }
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

    func testEveryPlanHasExactlyTheFiveFinalTabs() {
        for plan in [nil, "basic", "vip"] as [String?] {
            let app = launch(plan: plan)
            XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
            XCTAssertEqual(app.tabBars.buttons.allElementsBoundByIndex.map { $0.label }, Self.tabs, plan ?? "free")
            XCTAssertFalse(app.tabBars.buttons["DINCR"].exists, plan ?? "free")
            app.terminate()
        }
    }

    func testVipReachesEveryFormerDincrFunctionInItsNewHome() {
        let app = launch(plan: "vip", tab: "movements")
        open("movements.analysis", in: app)
        for (id, title) in [("analysis.summary", "Resumen del mes"), ("analysis.reports", "Reportes"), ("analysis.review", "Revisión del mes")] {
            open(id, in: app)
            XCTAssertTrue(app.navigationBars[title].waitForExistence(timeout: 10), title)
            app.navigationBars.buttons.element(boundBy: 0).tap()
        }
        app.tabBars.buttons["Patrimonio"].tap()
        for (id, title) in [("wealth.projections", "Proyecciones"), ("wealth.scenarios", "Escenarios")] {
            open(id, in: app)
            XCTAssertTrue(app.navigationBars[title].waitForExistence(timeout: 10), title)
            app.navigationBars.buttons.element(boundBy: 0).tap()
        }
        // DINCR hoy: the proactive advisor's changes are in Hoy → Para atender (and "Ver todas").
        app.tabBars.buttons["Hoy"].tap()
        XCTAssertTrue(element("home.attention", in: app).waitForExistence(timeout: 10))
    }

    func testTheGatesStayPerPlan() {
        let free = launch(tab: "movements")
        open("movements.analysis", in: free)
        XCTAssertTrue(element("analysis.summary", in: free).waitForExistence(timeout: 10))
        XCTAssertTrue(element("analysis.reports", in: free).label.contains("Disponible desde Basic"))
        XCTAssertTrue(element("analysis.review", in: free).label.contains("Disponible desde VIP"))
        free.tabBars.buttons["Patrimonio"].tap()
        XCTAssertTrue(element("wealth.projections", in: free).waitForExistence(timeout: 10))
        XCTAssertTrue(element("wealth.projections", in: free).label.contains("Disponible desde VIP"))
        XCTAssertTrue(element("wealth.scenarios", in: free).label.contains("Disponible desde VIP"))
        free.terminate()

        let basic = launch(plan: "basic", tab: "movements")
        open("movements.analysis", in: basic)
        XCTAssertTrue(element("analysis.reports", in: basic).waitForExistence(timeout: 10))
        XCTAssertFalse(element("analysis.reports", in: basic).label.contains("Disponible desde"))
        XCTAssertTrue(element("analysis.review", in: basic).label.contains("Disponible desde VIP"))
        open("analysis.reports", in: basic)
        XCTAssertTrue(basic.navigationBars["Reportes"].waitForExistence(timeout: 10))
    }

    func testTheOwnerKeepsTheFiveTabsAndJarvis() {
        let app = launch(role: "owner", tab: "profile")
        XCTAssertTrue(app.tabBars.firstMatch.waitForExistence(timeout: 10))
        XCTAssertEqual(app.tabBars.buttons.allElementsBoundByIndex.map { $0.label }, Self.tabs)
        open("profile.jarvis", in: app)
        XCTAssertTrue(element("jarvis.section.chat", in: app).waitForExistence(timeout: 10))
    }
}
