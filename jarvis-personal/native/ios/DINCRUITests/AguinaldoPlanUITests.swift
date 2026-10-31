import XCTest

/// AG-1 — Plan → Aguinaldo (the Owner's, read from mail): under the accrued amount, "¿En qué usarlo?"
/// lists the fixed split with why. Android twin: `AguinaldoPlanUiTest`. Fixture data only.
@MainActor
final class AguinaldoPlanUITests: XCTestCase {
    func testTheOwnerSeesWhatToUseTheAguinaldoFor() {
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrTab", "plan",
                               "-DincrPlan", "vip", "-DincrRole", "owner", "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        app.launch()
        let entry = app.descendants(matching: .any)["plan.aguinaldo"].firstMatch
        XCTAssertTrue(entry.waitForExistence(timeout: 10))
        entry.tap()
        let plan = app.descendants(matching: .any)["aguinaldo.plan"].firstMatch
        for _ in 0..<4 where !plan.waitForExistence(timeout: 3) { app.swipeUp() }
        XCTAssertTrue(plan.exists)
        XCTAssertTrue(app.staticTexts["¿En qué usarlo?"].exists)
    }
}
