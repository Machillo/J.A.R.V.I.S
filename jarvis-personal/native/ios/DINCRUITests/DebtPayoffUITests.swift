import XCTest

/// Debts → when each debt ends and the month all of them end (the backend's estimate, debt_payoff.py),
/// for every plan and the Owner. Android twin: `PlanRecoveryUiTest.everyPlanAndTheOwnerSeeWhenTheirDebtsEnd`.
/// Fixture data only.
final class DebtPayoffUITests: XCTestCase {
    private func launch(plan: String?, role: String?) -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrTab", "plan",
                               "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
            + (plan.map { ["-DincrPlan", $0] } ?? []) + (role.map { ["-DincrRole", $0] } ?? [])
        app.launch()
        return app
    }

    private func element(_ id: String, in app: XCUIApplication) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }

    private func text(_ content: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", content)).firstMatch
    }

    func testEveryPlanAndTheOwnerSeeWhenTheirDebtsEnd() {
        for (plan, role) in [(nil, nil), ("vip", nil), ("vip", "owner")] as [(String?, String?)] {
            let context = role ?? plan ?? "free"
            let app = launch(plan: plan, role: role)
            let debts = element("plan.debts", in: app)
            XCTAssertTrue(debts.waitForExistence(timeout: 10), context)
            if !debts.isHittable { app.swipeUp() }
            debts.tap()
            XCTAssertTrue(element("debts.payoff.summary", in: app).waitForExistence(timeout: 10), context)
            XCTAssertTrue(text("Libre de deudas aprox.", in: app).exists, context)
            XCTAssertTrue(element("debt.payoff.31", in: app).exists || element("debt.payoff.32", in: app).exists, "\(context): each debt says when it ends")
            XCTAssertTrue(text("cuotas", in: app).exists, context)
            app.terminate()
        }
    }
}
