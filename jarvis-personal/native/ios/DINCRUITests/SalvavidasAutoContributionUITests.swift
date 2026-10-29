import XCTest

/// Salvavidas → Aportes automáticos on synthetic fixture data: a VIP ticks the box, fills the plan,
/// saves once and sees the breakdown under the balance; unknown savings ask for today's balance;
/// the annual interest rate is the Owner's alone. Android: `SalvavidasAutoContributionUiTest`.
@MainActor
final class SalvavidasAutoContributionUITests: XCTestCase {
    private func launch(_ scenario: String, plan: String? = nil, role: String? = nil) -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", scenario, "-DincrSkipLogin", "-AppleLanguages", "(es)", "-AppleLocale", "es_CR", "-DincrTab", "plan"]
        if let plan { arguments += ["-DincrPlan", plan] }
        if let role { arguments += ["-DincrRole", role] }
        app.launchArguments = arguments
        app.launch()
        return app
    }

    private func element(_ identifier: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any)[identifier].firstMatch
    }

    /// Scrolls until the element is on screen and hittable.
    @discardableResult
    private func reveal(_ identifier: String, in app: XCUIApplication) -> XCUIElement {
        let target = element(identifier, in: app)
        XCTAssertTrue(target.waitForExistence(timeout: 10), "missing \(identifier)")
        for _ in 0..<8 where !target.isHittable { app.swipeUp() }
        XCTAssertTrue(target.isHittable, "\(identifier) is not reachable")
        return target
    }

    private func openSalvavidas(_ app: XCUIApplication) {
        let row = element("plan.salvavidas", in: app)
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        if !row.isHittable { app.swipeUp() }
        row.tap()
        XCTAssertTrue(element("salvavidas.coverage", in: app).waitForExistence(timeout: 10))
    }

    private func tick(_ app: XCUIApplication) {
        reveal("salvavidas.auto.enabled", in: app)
        let toggle = app.switches["salvavidas.auto.enabled"]
        // A row near the tab bar can swallow the tap: scroll a little and try again until it is on.
        for _ in 0..<3 where (toggle.value as? String) != "1" {
            toggle.coordinate(withNormalizedOffset: CGVector(dx: 0.95, dy: 0.5)).tap()
            if (toggle.value as? String) != "1" { app.swipeUp() }
        }
        XCTAssertEqual(toggle.value as? String, "1", "the box is ticked")
    }

    private func type(_ text: String, into identifier: String, in app: XCUIApplication) {
        let field = reveal(identifier, in: app)
        // A tap during a scroll's deceleration may not focus the field: tap until it has the keyboard.
        for _ in 0..<3 where !((field.value(forKey: "hasKeyboardFocus") as? Bool) ?? false) {
            field.tap()
            _ = app.keyboards.firstMatch.waitForExistence(timeout: 2)
        }
        field.typeText(text)
    }

    func testAVipTicksTheBoxSavesThePlanAndSeesTheBreakdown() {
        // The store account has declared savings, so no balance is asked for.
        let app = launch("store", plan: "vip")
        openSalvavidas(app)
        XCTAssertFalse(element("salvavidas.breakdown", in: app).exists, "no breakdown before a plan")
        XCTAssertFalse(element("salvavidas.auto.amount", in: app).exists, "the fields wait for the box")
        tick(app)
        type("10000", into: "salvavidas.auto.amount", in: app)
        XCTAssertFalse(element("salvavidas.auto.current", in: app).exists, "known savings are not asked again")
        XCTAssertFalse(element("salvavidas.auto.rate", in: app).exists, "the interest rate is never offered to a VIP")
        reveal("salvavidas.auto.save", in: app).tap()
        XCTAssertTrue(element("salvavidas.notice", in: app).waitForExistence(timeout: 10))
        app.swipeDown(); app.swipeDown()
        XCTAssertTrue(element("salvavidas.breakdown", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(element("salvavidas.breakdown.contributions", in: app).exists)
        XCTAssertTrue(element("salvavidas.breakdown.next", in: app).exists)
        XCTAssertFalse(element("salvavidas.breakdown.interest", in: app).exists, "no interest for a VIP")
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", "Según tu plan de aportes")).firstMatch.exists)
    }

    func testUnknownSavingsAskForTodaysBalance() {
        let app = launch("populated", plan: "vip")
        openSalvavidas(app)
        tick(app)
        XCTAssertTrue(reveal("salvavidas.auto.current", in: app).exists, "turning it on asks how much is saved today")
        XCTAssertFalse(element("salvavidas.auto.rate", in: app).exists)
    }

    func testTheOwnerHasTheInterestRate() {
        let app = launch("populated", role: "owner")
        openSalvavidas(app)
        reveal("salvavidas.auto.rate", in: app)
        tick(app)
        type("10000", into: "salvavidas.auto.amount", in: app)
        type("2,5", into: "salvavidas.auto.rate", in: app)
        reveal("salvavidas.auto.save", in: app).tap()
        XCTAssertTrue(element("salvavidas.notice", in: app).waitForExistence(timeout: 10))
        app.swipeDown(); app.swipeDown(); app.swipeDown()
        XCTAssertTrue(element("salvavidas.breakdown.interest", in: app).waitForExistence(timeout: 10))
    }
}
