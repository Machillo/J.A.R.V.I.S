import XCTest

/// Plan → Tu plan del mes: a VIP chooses whether investing is in the plan, off until they turn it on and
/// kept once chosen. Basic doesn't have it, and the Owner's plan has its own rules. Android: `InvestmentChoiceUiTest`.
@MainActor
final class InvestmentChoiceUITests: XCTestCase {
    private func openPlan(plan: String, role: String? = nil) -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrPlan", plan, "-DincrTab", "plan",
                               "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"] + (role.map { ["-DincrRole", $0] } ?? [])
        app.launch()
        let row = app.descendants(matching: .any)["plan.strategy"].firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 15))
        row.tap()
        return app
    }

    func testAVipTurnsItOnAndItStays() {
        let app = openPlan(plan: "vip")
        let choice = app.switches["plan.investmentChoice"]
        XCTAssertTrue(choice.waitForExistence(timeout: 15))
        for _ in 0..<6 where choice.frame.maxY > app.frame.maxY - 140 { app.swipeUp() }
        XCTAssertEqual(choice.value as? String, "0", "off until they turn it on")
        choice.coordinate(withNormalizedOffset: CGVector(dx: 0.95, dy: 0.5)).tap()
        let on = expectation(for: NSPredicate(format: "value == '1'"), evaluatedWith: choice)
        wait(for: [on], timeout: 10)
        app.navigationBars.buttons.element(boundBy: 0).tap()
        let row = app.descendants(matching: .any)["plan.strategy"].firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        row.tap()
        XCTAssertTrue(choice.waitForExistence(timeout: 15))
        XCTAssertEqual(choice.value as? String, "1", "kept once chosen")
    }

    func testBasicDoesNotHaveIt() {
        let app = openPlan(plan: "basic")
        XCTAssertTrue(app.descendants(matching: .any)["plan.month.budget"].waitForExistence(timeout: 15))
        XCTAssertFalse(app.switches["plan.investmentChoice"].exists)
    }

    func testTheOwnerDoesNotHaveIt() {
        let app = openPlan(plan: "vip", role: "owner")
        XCTAssertTrue(app.navigationBars.firstMatch.waitForExistence(timeout: 15))
        XCTAssertFalse(app.switches["plan.investmentChoice"].waitForExistence(timeout: 5))
    }
}
