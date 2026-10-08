import XCTest

/// UX-16 — plain financial language: the money left after commitments has one name everywhere
/// (no "margen"), and the monthly review says how each indicator moved in words, with its unit.
/// Android twin: `PlainLanguageUiTest`. Fixture data only.
final class PlainLanguageUITests: XCTestCase {
    private func launch(plan: String, tab: String? = nil, english: Bool = false) -> XCUIApplication {
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrPlan", plan]
        arguments += english ? ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"] : ["-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
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

    private func text(_ content: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", content)).firstMatch
    }

    func testHoySaysWhatIsLeftInSpanishAndEnglish() {
        for (english, left) in [(false, "Libre después de compromisos"), (true, "Left after commitments")] {
            let app = launch(plan: "vip", english: english)
            XCTAssertTrue(text(left, in: app).waitForExistence(timeout: 10), left)
            XCTAssertFalse(text(english ? "margin" : "Margen", in: app).exists)
            app.terminate()
        }
    }

    func testBasicPlanNamesWhatIsLeft() {
        let app = launch(plan: "basic", tab: "plan")
        open("plan.strategy", in: app)
        XCTAssertTrue(text("Libre después de tus compromisos", in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(text("Margen", in: app).exists)
    }

    func testTheMonthlyReviewSaysHowEachIndicatorMoved() {
        let app = launch(plan: "vip", tab: "movements")
        open("movements.analysis", in: app)
        open("analysis.review", in: app)
        XCTAssertTrue(text("Deuda total · mejoró", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Meses que cubre tu fondo de emergencia · sin cambios", in: app).exists)
        XCTAssertTrue(text("1 mes", in: app).exists)
        XCTAssertTrue(text("Ingresos menos gastos · empeoró", in: app).exists)
        XCTAssertFalse(text("months", in: app).exists)  // no raw unit codes
    }
}
