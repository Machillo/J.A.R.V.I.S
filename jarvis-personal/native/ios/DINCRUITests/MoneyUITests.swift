import XCTest

/// JARVIS → Mi dinero (Owner) on the fixture backend: the cycle (expected and received income, the
/// period's spending, the real balance) and the accounts (adding one, removing one after confirming).
/// Other roles never reach JARVIS (JarvisAccessUITests). Android: `MoneyUiTest`.
@MainActor
final class MoneyUITests: XCTestCase {
    private func launchOwner() -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrTab", "profile", "-DincrRole", "owner",
                               "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        app.launch()
        return app
    }

    private func element(_ identifier: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any)[identifier].firstMatch
    }

    private func text(_ content: String, in app: XCUIApplication) -> XCUIElement {
        app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", content)).firstMatch
    }

    private func tap(_ identifier: String, in app: XCUIApplication) {
        let target = element(identifier, in: app)
        XCTAssertTrue(target.waitForExistence(timeout: 10), "missing \(identifier)")
        for _ in 0..<6 where !target.isHittable { app.swipeUp() }
        target.tap()
    }

    private func openMoney(_ app: XCUIApplication) {
        tap("profile.jarvis", in: app)
        tap("jarvis.section.money", in: app)
        XCTAssertTrue(element("money.cycle", in: app).waitForExistence(timeout: 10))
    }

    func testTheCycleAndTheAccountsShow() {
        let app = launchOwner()
        openMoney(app)
        XCTAssertFalse(element("jarvis.restoring", in: app).exists, "no longer a placeholder")
        XCTAssertTrue(text("Ingresos esperados", in: app).exists)
        XCTAssertTrue(text("Saldo real", in: app).exists)
        XCTAssertTrue(element("money.accounts", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Cuenta de ejemplo", in: app).waitForExistence(timeout: 5))
        XCTAssertTrue(text("Ahorro en dólares", in: app).exists)
        XCTAssertTrue(text("No suma a tu patrimonio", in: app).exists)
    }

    func testANewAccountIsListed() {
        let app = launchOwner()
        openMoney(app)
        tap("money.add", in: app)
        let name = element("money.form.name", in: app)
        XCTAssertTrue(name.waitForExistence(timeout: 5))
        name.tap()
        name.typeText("Cuenta nueva de ejemplo")
        let balance = element("money.form.balance", in: app)
        balance.tap()
        balance.typeText("50000")
        element("money.form.save", in: app).tap()
        XCTAssertTrue(text("Cuenta guardada", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Cuenta nueva de ejemplo", in: app).waitForExistence(timeout: 10))
    }

    func testRemovingAnAccountAsksFirst() {
        let app = launchOwner()
        openMoney(app)
        XCTAssertTrue(text("Detectada por correo", in: app).waitForExistence(timeout: 10))
        tap("money.delete.903", in: app)
        let confirm = app.sheets.buttons["Quitar"]
        if confirm.waitForExistence(timeout: 3) {
            confirm.tap()
        } else {
            app.buttons.matching(NSPredicate(format: "label == %@ AND NOT (identifier BEGINSWITH %@)", "Quitar", "money.delete.")).firstMatch.tap()
        }
        XCTAssertTrue(text("Cuenta quitada", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Cuenta de ejemplo", in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(text("Detectada por correo", in: app).exists)
    }
}
