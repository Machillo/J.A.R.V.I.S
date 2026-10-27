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
            // What has been paid of all the debts and what is left.
            XCTAssertTrue(element("debts.progress.total", in: app).exists, "\(context): the total progress")
            XCTAssertTrue(text("Pagado", in: app).exists && text("Te falta el", in: app).exists, context)
            XCTAssertTrue(element("debt.progress.31", in: app).exists || element("debt.progress.32", in: app).exists, "\(context): each debt's progress")
            // Owner and VIP read their strategy's debt-free date; Free only the installments' estimate.
            let strategy = element("debts.strategy.date", in: app)
            if plan == nil {
                XCTAssertFalse(strategy.exists, "Free has no strategy")
                XCTAssertTrue(text("Libre de deudas aprox.", in: app).exists, context)
            } else {
                XCTAssertTrue(strategy.waitForExistence(timeout: 10), "\(context): the strategy's date")
                XCTAssertTrue(text("Libre de deudas según tu estrategia", in: app).exists, context)
                XCTAssertTrue(text("Solo con las cuotas", in: app).exists, context)
            }
            XCTAssertTrue(element("debt.payoff.31", in: app).exists || element("debt.payoff.32", in: app).exists, "\(context): each debt says when it ends")
            XCTAssertTrue(text("cuotas", in: app).exists, context)
            app.terminate()
        }
    }
}
