import XCTest

/// JARVIS → Control de dinero (Owner) on the fixture backend: who owes the Owner money (two invented
/// people), their history, recording a payment and a new collection. Other roles never reach JARVIS
/// (JarvisAccessUITests). Android: `MoneyControlUiTest`.
@MainActor
final class MoneyControlUITests: XCTestCase {
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

    private func openMoneyControl(_ app: XCUIApplication) {
        tap("profile.jarvis", in: app)
        tap("jarvis.section.money_control", in: app)
        XCTAssertTrue(element("money.summary", in: app).waitForExistence(timeout: 10))
    }

    func testTheOwnerSeesWhoOwesHimAndTheirHistory() {
        let app = launchOwner()
        openMoneyControl(app)
        XCTAssertFalse(element("jarvis.restoring", in: app).exists, "no longer a placeholder")
        XCTAssertTrue(text("Te deben", in: app).exists)
        XCTAssertTrue(text("2 personas con saldo pendiente", in: app).exists)
        XCTAssertTrue(text("Ana de ejemplo", in: app).exists)
        XCTAssertTrue(text("Luis de ejemplo", in: app).exists)
        XCTAssertTrue(text("Tarjeta adicional", in: app).exists)
        tap("money.history.7002", in: app)
        XCTAssertTrue(text("Compra con tarjeta adicional", in: app).waitForExistence(timeout: 5))
    }

    func testRecordingAPaymentSettlesThePerson() {
        let app = launchOwner()
        openMoneyControl(app)
        tap("money.pay.7001", in: app)
        let amount = element("money.payment.amount", in: app)
        XCTAssertTrue(amount.waitForExistence(timeout: 5))
        amount.tap()
        amount.typeText("35000")
        element("money.payment.save", in: app).tap()
        XCTAssertTrue(text("Pago registrado", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Al día", in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(element("money.pay.7001", in: app).exists, "a settled person has nothing to pay")
    }

    func testANewCollectionAddsThePerson() {
        let app = launchOwner()
        openMoneyControl(app)
        tap("money.add", in: app)
        let person = element("money.entry.person", in: app)
        XCTAssertTrue(person.waitForExistence(timeout: 5))
        person.tap()
        person.typeText("Marta de ejemplo")
        let amount = element("money.entry.amount", in: app)
        amount.tap()
        amount.typeText("12000")
        element("money.entry.save", in: app).tap()
        XCTAssertTrue(text("Cobro registrado", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Marta de ejemplo", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("3 personas con saldo pendiente", in: app).exists)
    }
}
