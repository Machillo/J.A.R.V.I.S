import XCTest

/// RT-1 — Plan → Retiro: VIP and the Owner read their retirement savings in simple words and can edit
/// them; Free and Basic see the row locked. Android twin: `RetirementUiTest`. Fixture data only.
@MainActor
final class RetirementUITests: XCTestCase {
    private func launch(plan: String?) -> XCUIApplication {
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrTab", "plan",
                         "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        if let plan { arguments += ["-DincrPlan", plan] }
        app.launchArguments = arguments
        app.launch()
        return app
    }

    private func element(_ id: String, in app: XCUIApplication) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }

    func testVipReadsItsRetirementSavings() {
        let app = launch(plan: "vip")
        let row = element("plan.retirement", in: app)
        for _ in 0..<4 where !(row.waitForExistence(timeout: 3) && row.isHittable) { app.swipeUp() }
        row.tap()
        let reading = element("retirement.reading", in: app)
        XCTAssertTrue(reading.waitForExistence(timeout: 10))
        XCTAssertTrue(reading.label.contains("ahorrado para tu retiro"), reading.label)
    }

    func testFreeSeesItLocked() {
        let app = launch(plan: nil)
        let row = element("plan.retirement", in: app)
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        XCTAssertTrue(row.label.contains("Disponible desde VIP"), row.label)
    }
}
