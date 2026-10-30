import XCTest

/// Plan → Gastos fijos (FX-1) on synthetic fixture data: the Owner sees his fixed expenses, adds one
/// and removes one; a VIP manages its recurring expenses there (expenses only, no type to choose);
/// Basic sees the row locked. Android: `FixedExpensesUiTest`.
@MainActor
final class FixedExpensesUITests: XCTestCase {
    private func launch(plan: String, role: String? = nil) -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-AppleLanguages", "(es)", "-AppleLocale", "es_CR",
                         "-DincrTab", "plan", "-DincrPlan", plan]
        if let role { arguments += ["-DincrRole", role] }
        app.launchArguments = arguments
        app.launch()
        return app
    }

    private func element(_ identifier: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any)[identifier].firstMatch
    }

    private func openFixedExpenses(_ app: XCUIApplication) {
        let row = element("plan.fixedExpenses", in: app)
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        for _ in 0..<4 where !row.isHittable { app.swipeUp() }
        row.tap()
    }

    func testTheOwnerAddsAndRemovesAFixedExpense() {
        let app = launch(plan: "vip", role: "owner")
        openFixedExpenses(app)
        XCTAssertTrue(element("fixedExpenses.row.9101", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(element("fixedExpenses.total", in: app).exists)

        element("fixedExpenses.add", in: app).tap()
        let name = app.textFields["fixedExpenses.name"]
        XCTAssertTrue(name.waitForExistence(timeout: 5))
        name.tap(); name.typeText("Agua de ejemplo")
        let amount = app.textFields["fixedExpenses.amount"]
        amount.tap(); amount.typeText("9000")
        app.buttons["fixedExpenses.save"].tap()
        XCTAssertTrue(element("fixedExpenses.notice", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", "Agua de ejemplo")).firstMatch.waitForExistence(timeout: 10))

        let remove = element("fixedExpenses.remove.9101", in: app)
        for _ in 0..<4 where !remove.isHittable { app.swipeUp() }
        remove.tap()
        app.buttons["fixedExpenses.confirmRemove"].firstMatch.tap()
        XCTAssertTrue(element("fixedExpenses.row.9101", in: app).waitForNonExistence(timeout: 10))
    }

    func testAVipManagesItsRecurringExpensesThere() {
        let app = launch(plan: "vip")
        openFixedExpenses(app)
        XCTAssertTrue(app.navigationBars["Gastos fijos"].waitForExistence(timeout: 10))
        app.buttons["recurring.add"].tap()
        XCTAssertTrue(app.textFields["recurring.name"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.segmentedControls.buttons["Ingreso"].exists, "a fixed expense is always an expense")
    }

    func testBasicSeesItLocked() {
        let app = launch(plan: "basic")
        let row = element("plan.fixedExpenses", in: app)
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", "Disponible desde")).firstMatch.exists)
    }
}
