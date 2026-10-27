import XCTest

/// "Pagado con" in the expense editor, on the fixture backend: the user's own card is offered, the
/// expense saves with it, and an income never shows the picker. Synthetic data only.
@MainActor
final class PaidWithUITests: XCTestCase {
    private func launch() -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrPlan", "vip",
                               "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        app.launch()
        return app
    }

    func testAnExpenseSaysWhichOwnCardPaidIt() {
        let app = launch()
        app.tabBars.buttons["Movimientos"].firstMatch.tap()
        let add = app.buttons["movements.add"]
        XCTAssertTrue(add.waitForExistence(timeout: 5))
        add.tap()

        let picker = app.buttons["editor.paidWith"]
        XCTAssertTrue(picker.waitForExistence(timeout: 5))
        picker.tap()
        let card = app.buttons["BAC · Tarjeta de crédito ••5678"]
        XCTAssertTrue(card.waitForExistence(timeout: 3))
        XCTAssertFalse(app.buttons["BAC · Cuenta de ahorro ••1234"].exists, "a pending account is not offered")
        card.tap()

        let amount = app.textFields["editor.amount"]
        amount.tap()
        amount.typeText("12500")
        let description = app.textFields["editor.description"]
        description.tap()
        description.typeText("Supermercado con tarjeta")
        app.buttons["editor.save"].tap()
        XCTAssertTrue(app.buttons["editor.save"].waitForNonExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["Supermercado con tarjeta"].waitForExistence(timeout: 10))
    }

    func testAnIncomeHasNoPaidWith() {
        let app = launch()
        app.tabBars.buttons["Movimientos"].firstMatch.tap()
        let add = app.buttons["movements.add"]
        XCTAssertTrue(add.waitForExistence(timeout: 5))
        add.tap()
        XCTAssertTrue(app.buttons["editor.paidWith"].waitForExistence(timeout: 5))
        app.buttons["Ingreso"].tap()
        XCTAssertTrue(app.buttons["editor.paidWith"].waitForNonExistence(timeout: 3))
    }
}
