import XCTest

/// Patrimonio → Escenarios (VIP): the user picks the what-if (pay a debt off, an extra payment, a new
/// debt) and sees how much would be left each month. Fixture data; nothing is saved.
final class DebtScenarioUITests: XCTestCase {
    private func launch() -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrTab", "wealth",
                               "-DincrPlan", "vip", "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        app.launch()
        return app
    }

    private func element(_ identifier: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any)[identifier].firstMatch
    }

    private func openScenarios(_ app: XCUIApplication) {
        let entry = element("wealth.scenarios", in: app)
        XCTAssertTrue(entry.waitForExistence(timeout: 15))
        entry.tap()
        XCTAssertTrue(app.navigationBars["Escenarios"].waitForExistence(timeout: 10))
    }

    private func choose(_ option: String, from identifier: String, in app: XCUIApplication) {
        let menu = element(identifier, in: app)
        XCTAssertTrue(menu.waitForExistence(timeout: 10), identifier)
        menu.tap()
        let item = app.buttons[option].firstMatch
        XCTAssertTrue(item.waitForExistence(timeout: 5), option)
        item.tap()
    }

    /// "Simular" once the menu that was just used has closed (a tap while it closes finds nothing).
    private func run(_ app: XCUIApplication) {
        let button = element("scenario.run", in: app)
        XCTAssertTrue(button.waitForExistence(timeout: 10), "scenario.run")
        if !button.isHittable { app.swipeUp() }
        button.tap()
    }

    func testPayingADebtOffShowsTheMonthWithoutItsPayment() {
        let app = launch()
        openScenarios(app)
        choose("Pagar una deuda completa", from: "scenario.kind", in: app)
        let debt = element("scenario.debt", in: app)
        XCTAssertTrue(debt.waitForExistence(timeout: 10))
        debt.tap()
        // The first real debt in the menu (after "Elegí una deuda").
        let first = app.buttons.matching(NSPredicate(format: "label != %@", "Elegí una deuda")).element(boundBy: 0)
        XCTAssertTrue(first.waitForExistence(timeout: 5))
        first.tap()
        run(app)
        XCTAssertTrue(element("scenario.result.leftover", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["Pago único"].exists)
    }

    func testANewDebtNeedsAPaymentOrItsTerms() {
        let app = launch()
        openScenarios(app)
        choose("Agregar una deuda nueva", from: "scenario.kind", in: app)
        let amount = element("scenario.amount", in: app)
        XCTAssertTrue(amount.waitForExistence(timeout: 10))
        amount.tap()
        amount.typeText("1000000")
        run(app)
        XCTAssertTrue(app.staticTexts["Indicá la cuota, o la tasa y el plazo."].waitForExistence(timeout: 5))
        let payment = element("scenario.new.payment", in: app)
        payment.tap()
        payment.typeText("50000")
        run(app)
        XCTAssertTrue(element("scenario.result.leftover", in: app).waitForExistence(timeout: 10))
    }
}
