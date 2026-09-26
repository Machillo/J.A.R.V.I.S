import XCTest

/// End-to-end flows on synthetic fixture data (no backend, no real account).
final class DINCRUITests: XCTestCase {
    override func setUp() {
        continueAfterFailure = false
    }

    private func launch(_ scenario: String = "populated", skipLogin: Bool = true, extra: [String] = []) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", scenario, "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"] + (skipLogin ? ["-DincrSkipLogin"] : []) + extra
        app.launch()
        return app
    }

    func testLoginLeadsToHome() {
        let app = launch(skipLogin: false)
        let google = app.buttons["login.google"]
        XCTAssertTrue(google.waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["login.apple"].exists)
        google.tap()
        XCTAssertTrue(app.staticTexts["Disponible este mes"].waitForExistence(timeout: 5))
    }

    func testHomeShowsKeyFigureAndSections() {
        let app = launch()
        XCTAssertTrue(app.staticTexts["Disponible este mes"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Ingresos y gastos"].exists)
        XCTAssertTrue(app.staticTexts["En qué se va el dinero"].exists)
    }

    func testAddExpenseValidatesAndSaves() {
        let app = launch()
        app.tabBars.buttons["Movimientos"].tap()
        let add = app.buttons["movements.add"]
        XCTAssertTrue(add.waitForExistence(timeout: 5))
        add.tap()

        // Empty form: both fields fail, the summary lists them.
        app.buttons["editor.save"].tap()
        XCTAssertTrue(app.staticTexts["Revisá 2 campos"].waitForExistence(timeout: 2))

        // A mistyped decimal is rejected, never silently multiplied.
        let amount = app.textFields["editor.amount"]
        amount.tap()
        amount.typeText("1.5.2")
        let description = app.textFields["editor.description"]
        description.tap()
        description.typeText("Panadería")
        app.buttons["editor.save"].tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'Escribí un monto'")).firstMatch.waitForExistence(timeout: 2))

        amount.tap()
        amount.clearAndType("4.250")
        app.buttons["editor.save"].tap()

        // Durable outcome: the sheet closes and the new row is listed. (The "Gasto guardado"
        // status is intentionally transient, 4 s, so it is not a reliable assertion target.)
        XCTAssertTrue(app.buttons["editor.save"].waitForNonExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["Panadería"].waitForExistence(timeout: 10))
    }

    func testEmptyAccountTeachesTheFirstAction() {
        let app = launch("empty")
        XCTAssertTrue(app.staticTexts["Todavía no hay movimientos"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["Agregar movimiento"].exists)
    }

    func testFailingBackendShowsRecovery() {
        let app = launch("failing", skipLogin: true)
        XCTAssertTrue(app.staticTexts["No pudimos cargar tu cuenta"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["Intentar de nuevo"].exists)
        XCTAssertTrue(app.buttons["Cerrar sesión"].exists)
    }

    func testNewUserGoesThroughProfileSetup() {
        let app = launch("newUser")
        let next = app.buttons["setup.continue"]
        XCTAssertTrue(next.waitForExistence(timeout: 5))
        next.tap() // name prefilled from the account
        app.buttons["Tomar control de mis finanzas"].tap()
        next.tap()
        next.tap()
        XCTAssertTrue(app.buttons["Entrar a DINCR"].waitForExistence(timeout: 2))
        app.buttons["Entrar a DINCR"].tap()
        XCTAssertTrue(app.staticTexts["Disponible este mes"].waitForExistence(timeout: 5))
    }
}

extension XCUIElement {
    func clearAndType(_ text: String) {
        guard let current = value as? String, !current.isEmpty else { typeText(text); return }
        typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: current.count))
        typeText(text)
    }
}
