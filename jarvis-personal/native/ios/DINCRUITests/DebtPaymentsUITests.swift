import XCTest

/// DEB-07a — Plan → Deudas → "Ver pagos": the payments recorded in DINCR for a debt, newest first,
/// with the amount actually applied. A debt without payments says so. Android twin:
/// `DebtPaymentsUiTest`. Fixture data only.
final class DebtPaymentsUITests: XCTestCase {
    private func launch() -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin",
                               "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        app.launch()
        return app
    }

    private func element(_ id: String, in app: XCUIApplication) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }

    private func tap(_ id: String, in app: XCUIApplication) {
        let target = element(id, in: app)
        XCTAssertTrue(target.waitForExistence(timeout: 10), "missing \(id)")
        target.tap()
    }

    func testARecordedPaymentAppearsInTheDebtsHistory() {
        let app = launch()
        tap("home.debts", in: app)
        tap("debt.history.31", in: app)
        XCTAssertTrue(element("debt.payments.empty", in: app).waitForExistence(timeout: 10), "no payment recorded yet: said in words")
        app.buttons["Cerrar"].tap()

        tap("debt.pay.31", in: app)
        let field = app.textFields["amount.field"]
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        field.tap()
        field.typeText("10.000")
        app.buttons["amount.save"].tap()
        XCTAssertTrue(element("plan.notice", in: app).waitForExistence(timeout: 10))

        tap("debt.history.31", in: app)
        let list = element("debt.payments.list", in: app)
        XCTAssertTrue(list.waitForExistence(timeout: 10))
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", "10.000")).firstMatch.exists,
                      "the amount applied")
        XCTAssertFalse(element("debt.payments.empty", in: app).exists)
    }
}
