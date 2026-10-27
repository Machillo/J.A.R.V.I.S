import XCTest

/// JARVIS → Patrimonio (Owner) on the fixture backend: the investments (the invented portfolio, its
/// positions, "Actualizar desde IBKR") and the businesses (creating one and recording a movement on
/// it). Other roles never reach JARVIS (JarvisAccessUITests). Android: `OwnerWealthUiTest`.
@MainActor
final class OwnerWealthUITests: XCTestCase {
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

    private func tap(_ target: XCUIElement, _ name: String, in app: XCUIApplication) {
        XCTAssertTrue(target.waitForExistence(timeout: 10), "missing \(name)")
        for _ in 0..<6 where !target.isHittable { app.swipeUp() }
        target.tap()
    }

    private func tap(_ identifier: String, in app: XCUIApplication) { tap(element(identifier, in: app), identifier, in: app) }

    private func type(_ value: String, into identifier: String, in app: XCUIApplication) {
        let field = element(identifier, in: app)
        XCTAssertTrue(field.waitForExistence(timeout: 5), "missing \(identifier)")
        field.tap()
        field.typeText(value)
    }

    private func openWealth(_ app: XCUIApplication) {
        tap("profile.jarvis", in: app)
        tap("jarvis.section.wealth", in: app)
    }

    func testTheOwnerSeesThePortfolioAndItsPositions() {
        let app = launchOwner()
        openWealth(app)
        XCTAssertTrue(element("wealth.investments", in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(element("jarvis.restoring", in: app).exists, "no longer a placeholder")
        XCTAssertTrue(text("Valor de mercado", in: app).exists)
        XCTAssertTrue(text("Rendimiento", in: app).exists)
        XCTAssertTrue(text("Actualizado hace 5 h", in: app).exists)
        XCTAssertFalse(text("Todavía no hay datos de tu portafolio", in: app).exists)
        XCTAssertTrue(text("ETF de ejemplo", in: app).exists)
        XCTAssertTrue(text("Acción de ejemplo", in: app).exists)
        tap("wealth.sync", in: app)
        XCTAssertTrue(text("Portafolio actualizado", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(element("wealth.netWorth", in: app).exists)
    }

    func testTheOwnerCreatesABusinessAndRecordsAMovement() {
        let app = launchOwner()
        openWealth(app)
        XCTAssertTrue(element("wealth.investments", in: app).waitForExistence(timeout: 10))
        app.buttons["Negocios"].firstMatch.tap()
        XCTAssertTrue(element("wealth.businesses", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Negocio de ejemplo", in: app).exists)
        XCTAssertTrue(element("wealth.business.9101", in: app).exists)

        tap("wealth.addBusiness", in: app)
        type("Negocio nuevo de ejemplo", into: "wealth.business.name", in: app)
        element("wealth.business.save", in: app).tap()
        XCTAssertTrue(text("Negocio creado", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Negocio nuevo de ejemplo", in: app).waitForExistence(timeout: 10))

        let record = app.descendants(matching: .any)
            .matching(NSPredicate(format: "identifier BEGINSWITH 'wealth.addMovement.' AND identifier != 'wealth.addMovement.9101'")).firstMatch
        tap(record, "the new business's Registrar movimiento", in: app)
        XCTAssertTrue(text("También se registra en tus movimientos.", in: app).waitForExistence(timeout: 5))
        type("25000", into: "wealth.movement.amount", in: app)
        type("Primera venta de ejemplo", into: "wealth.movement.description", in: app)
        element("wealth.movement.save", in: app).tap()
        XCTAssertTrue(text("Movimiento registrado", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Primera venta de ejemplo", in: app).waitForExistence(timeout: 10))
    }
}
