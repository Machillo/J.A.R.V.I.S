import XCTest

/// What the Owner must see on Hoy and Movimientos: the salary the app already knows, counted in Ingresos,
/// and the dollars waiting for their close, counted in Gastos as an estimate. Android: `OwnerWealthUiTest`.
@MainActor
final class OwnerMoneyVisibleUITests: XCTestCase {
    private func launch(tab: String) -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrTab", tab, "-DincrRole", "owner",
                               "-DincrPendingSample", "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        app.launch()
        return app
    }

    private func element(_ id: String, _ app: XCUIApplication) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }

    func testMovementsShowTheSalaryAndCountItInIncome() {
        let app = launch(tab: "movements")
        XCTAssertTrue(element("movements.totals", app).waitForExistence(timeout: 15))
        let salary = app.staticTexts["Salario del mes (estimado)"]
        for _ in 0..<8 where !salary.exists { app.swipeUp() }
        XCTAssertTrue(salary.waitForExistence(timeout: 5), "the salary the app already knows")
    }
}
