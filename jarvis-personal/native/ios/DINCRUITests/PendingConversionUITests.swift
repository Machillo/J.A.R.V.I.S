import XCTest

/// A dollar expense that waits for the close, on the fixture backend: the editor offers "Convertir al
/// cierre" (on by default, no rate asked), and Movimientos lists it apart with its dollar total instead
/// of a colones amount. Turning it off asks for the rate again. Synthetic data only.
@MainActor
final class PendingConversionUITests: XCTestCase {
    private func launch() -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrPlan", "vip",
                               "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        app.launch()
        return app
    }

    private func openEditorInDollars(_ app: XCUIApplication) {
        app.tabBars.buttons["Movimientos"].firstMatch.tap()
        let add = app.buttons["movements.add"]
        XCTAssertTrue(add.waitForExistence(timeout: 5))
        add.tap()
        let dollars = app.segmentedControls["editor.currency"].buttons["USD"]
        XCTAssertTrue(dollars.waitForExistence(timeout: 5))
        dollars.tap()
    }

    func testADollarExpenseWaitsForTheCloseAndIsListedApart() {
        let app = launch()
        openEditorInDollars(app)
        let waits = app.switches["editor.waitForClose"]
        XCTAssertTrue(waits.waitForExistence(timeout: 5))
        XCTAssertEqual(waits.value as? String, "1", "a dollar expense waits for the close by default")
        XCTAssertFalse(app.textFields["editor.rate"].exists, "no rate is asked while it waits")

        let amount = app.textFields["editor.amount"]
        amount.tap()
        amount.typeText("120")
        let description = app.textFields["editor.description"]
        description.tap()
        description.typeText("Hotel en dólares")
        app.buttons["editor.save"].tap()
        XCTAssertTrue(app.buttons["editor.save"].waitForNonExistence(timeout: 10))

        let total = app.descendants(matching: .any)["movements.pending.total.USD"]
        XCTAssertTrue(total.waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["Hotel en dólares"].exists)
        XCTAssertTrue(app.staticTexts["En dólares · se convierten al cierre"].exists || app.staticTexts["EN DÓLARES · SE CONVIERTEN AL CIERRE"].exists)
    }

    func testTurningItOffAsksForTheRate() {
        let app = launch()
        openEditorInDollars(app)
        let waits = app.switches["editor.waitForClose"]
        XCTAssertTrue(waits.waitForExistence(timeout: 5))
        waits.switches.firstMatch.exists ? waits.switches.firstMatch.tap() : waits.tap()
        XCTAssertTrue(app.textFields["editor.rate"].waitForExistence(timeout: 3))
    }
}
