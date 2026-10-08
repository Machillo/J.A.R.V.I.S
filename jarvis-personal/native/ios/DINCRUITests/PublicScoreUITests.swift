import XCTest

/// K-2 — no public screen shows the financial-health score until it has a canonical calculation
/// (P3.7): Movimientos → Análisis → Revisión del mes keeps its other indicators and its next step
/// but not the score; the Owner keeps it in JARVIS → Análisis financiero. Android twin:
/// `PublicScoreUiTest`. Fixture data only.
final class PublicScoreUITests: XCTestCase {
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

    private func element(_ identifier: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any)[identifier].firstMatch
    }

    private func open(_ identifier: String, in app: XCUIApplication) {
        let target = element(identifier, in: app)
        XCTAssertTrue(target.waitForExistence(timeout: 10), "missing \(identifier)")
        if !target.isHittable { app.swipeUp() }
        target.tap()
    }

    private func contains(_ text: String, in app: XCUIApplication) -> Bool {
        app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS[c] %@", text)).count > 0
    }

    func testTheMonthlyReviewKeepsItsIndicatorsWithoutTheScore() {
        for (plan, role) in [("vip", nil), (nil, "owner")] as [(String?, String?)] {
            let app = launch(plan: plan, role: role, tab: "movements")
            open("movements.analysis", in: app)
            open("analysis.review", in: app)
            XCTAssertTrue(app.navigationBars["Revisión del mes"].waitForExistence(timeout: 10))
            XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Deuda total")).firstMatch.waitForExistence(timeout: 10), role ?? "vip")
            XCTAssertTrue(contains("Ingresos menos gastos", in: app))
            XCTAssertTrue(contains("Pagá extra a la tarjeta", in: app))  // the next step stays
            for hidden in ["Salud financiera", "/100", "points", "puntos"] { XCTAssertFalse(contains(hidden, in: app), "\(role ?? "vip"): \(hidden)") }
            app.terminate()
        }
    }

    func testTheOwnerKeepsTheScoreInJarvis() {
        let app = launch(role: "owner", tab: "profile")
        open("profile.jarvis", in: app)
        open("jarvis.section.analysis", in: app)
        let health = element("jarvis.analysis.health", in: app)
        if !health.waitForExistence(timeout: 10) { app.swipeUp() }
        XCTAssertTrue(health.waitForExistence(timeout: 10))
        XCTAssertTrue(contains("/100", in: app))
    }
}
