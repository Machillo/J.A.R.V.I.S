import XCTest

/// JARVIS → Registros (Owner) on the fixture backend: the timeline (balance today, the dated
/// events and the balance they leave) and the reconciliation (an account to review, confirming its
/// real balance). Other roles never reach JARVIS (JarvisAccessUITests). Android: `RecordsUiTest`.
@MainActor
final class RecordsUITests: XCTestCase {
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

    private func openRecords(_ app: XCUIApplication) {
        tap("profile.jarvis", in: app)
        tap("jarvis.section.records", in: app)
    }

    func testTheTimelineShowsTheBalanceAndTheDatedEvents() {
        let app = launchOwner()
        openRecords(app)
        XCTAssertTrue(element("records.timeline.summary", in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(element("jarvis.restoring", in: app).exists, "no longer a placeholder")
        XCTAssertTrue(text("Disponible hoy", in: app).exists)
        XCTAssertTrue(text("Cuota · Préstamo de ejemplo", in: app).exists)
        XCTAssertTrue(text("Ingreso de salario", in: app).exists)
        XCTAssertTrue(text("Queda:", in: app).exists)
    }

    func testConfirmingTheRealBalanceSettlesTheAccount() {
        let app = launchOwner()
        openRecords(app)
        app.buttons["Conciliación"].firstMatch.tap()
        XCTAssertTrue(element("records.reconciliation.summary", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("1 cuenta para revisar", in: app).exists)
        XCTAssertTrue(text("cuentas sin saldo registrado no se comparan", in: app).exists)
        tap("records.confirm.801", in: app)
        let amount = element("records.confirm.amount", in: app)
        XCTAssertTrue(amount.waitForExistence(timeout: 5))
        amount.tap()
        amount.typeText("310000")
        element("records.confirm.save", in: app).tap()
        XCTAssertTrue(text("Saldo confirmado", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Todas tus cuentas cuadran.", in: app).waitForExistence(timeout: 10))
    }
}
