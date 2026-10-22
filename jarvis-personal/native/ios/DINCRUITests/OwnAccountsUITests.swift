import XCTest

/// Own accounts from the app (Patrimonio → Cuentas): an own account no notice came from is added with its
/// institution, last 4 digits and currency, and any account can be answered "No la reconozco" (never
/// treated as own). Fixture data only. Android twin: `OwnAccountsUiTest`.
@MainActor
final class OwnAccountsUITests: XCTestCase {
    private func launch() -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrPlan", "vip",
                               "-DincrTab", "wealth", "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        app.launch()
        return app
    }

    private func element(_ identifier: String, in app: XCUIApplication) -> XCUIElement { app.descendants(matching: .any)[identifier].firstMatch }

    private func open(_ identifier: String, in app: XCUIApplication) {
        let target = element(identifier, in: app)
        XCTAssertTrue(target.waitForExistence(timeout: 10), "missing \(identifier)")
        if !target.isHittable { app.swipeUp() }
        target.tap()
    }

    private func text(_ content: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", content)).firstMatch
    }

    func testAnOwnAccountNoNoticeCameFromIsAddedAndShownAsOwn() {
        let app = launch()
        open("wealth.accounts", in: app)
        open("accounts.declare", in: app)
        open("declare.institution", in: app)
        app.buttons["MultiMoney"].firstMatch.tap()
        let last4 = app.textFields["declare.last4"]
        XCTAssertTrue(last4.waitForExistence(timeout: 5))
        last4.tap()
        last4.typeText("6281")
        app.buttons["Dólares"].firstMatch.tap()
        open("declare.save", in: app)
        XCTAssertTrue(element("accounts.notice", in: app).waitForExistence(timeout: 10))
        open("accounts.bank.multimoney", in: app)
        XCTAssertTrue(text("•••• 6281", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Es mía", in: app).exists)
    }

    func testAnAccountCanBeAnsweredIDontRecogniseIt() {
        let app = launch()
        open("wealth.accounts", in: app)
        open("accounts.bank.bac", in: app)
        open("accounts.change.1", in: app)
        app.buttons["No la reconozco"].firstMatch.tap()
        XCTAssertTrue(text("No la reconozco", in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(element("accounts.own.1", in: app).exists, "answered: no longer offered as unanswered")
    }
}
