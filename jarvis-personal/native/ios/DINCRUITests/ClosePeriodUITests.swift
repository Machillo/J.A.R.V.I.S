import XCTest

/// The close (3d) on the fixture backend: a dollar expense from last month waits in its month's close,
/// the close asks for one rate, shows the colones total and converts it into a colones movement.
/// Synthetic data only.
@MainActor
final class ClosePeriodUITests: XCTestCase {
    func testAnEndedCloseConvertsWithOneRate() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrPlan", "vip",
                               "-DincrPendingSample", "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        app.launch()
        app.tabBars.buttons["Movimientos"].firstMatch.tap()

        let close = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "movements.pending.close.month:")).firstMatch
        XCTAssertTrue(close.waitForExistence(timeout: 10))
        close.tap()

        let rate = app.textFields["close.rate"]
        XCTAssertTrue(rate.waitForExistence(timeout: 5))
        for _ in 0..<3 {
            rate.tap()
            if rate.value(forKey: "hasKeyboardFocus") as? Bool == true { break }
        }
        rate.clearAndType("510")
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Se registran ₡61")).firstMatch.waitForExistence(timeout: 5))
        app.buttons["close.save"].tap()
        XCTAssertTrue(app.buttons["close.save"].waitForNonExistence(timeout: 10))

        // Converted: no longer waiting (it is now a colones movement of last month, further down the list).
        let status = app.descendants(matching: .any).matching(NSPredicate(format: "label BEGINSWITH %@", "Convertidos 1 gasto(s): ₡61")).firstMatch
        XCTAssertTrue(status.waitForExistence(timeout: 10))
        XCTAssertTrue(close.waitForNonExistence(timeout: 10))
    }
}
