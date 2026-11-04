import XCTest

/// Own accounts from the app (Patrimonio → Cuentas): an own account no notice came from is added with its
/// institution, last 4 digits and currency, and any account can be answered "No la reconozco" (never
/// treated as own). Fixture data only. Android twin: `OwnAccountsUiTest`.
@MainActor
final class OwnAccountsUITests: XCTestCase {
    private func launch() -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrPlan", "vip", "-DincrMailLeftovers",
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

    /// The Owner adds a bank: pick it, confirm what the mail showed, see it listed. Only the Owner has the flow.
    func testTheOwnerAddsABankThroughTheGuidedFlow() {
        let app = launchForAddBank(role: "owner")
        XCTAssertFalse(element("accounts.declare", in: app).exists)
        open("accounts.addBank", in: app)
        open("addBank.bank.bac", in: app)
        XCTAssertTrue(element("addBank.account.1", in: app).waitForExistence(timeout: 10), "the detected account, chosen")
        XCTAssertTrue(element("addBank.account.1", in: app).isSelected)
        XCTAssertFalse(element("addBank.account.2", in: app).isEnabled, "already the Owner's")
        open("addBank.add", in: app)
        XCTAssertTrue(element("addBank.done", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(element("addBank.done", in: app).label.contains("2 cuentas"))
        open("addBank.another", in: app)
        open("addBank.bank.bn", in: app)
        XCTAssertTrue(element("addBank.none", in: app).waitForExistence(timeout: 10), "nothing in the mail: said, and by hand instead")
        XCTAssertTrue(element("addBank.review.manual", in: app).exists)
    }

    func testAVipKeepsTheOwnAccountFormAndNoGuidedFlow() {
        let app = launchForAddBank(role: nil)
        XCTAssertTrue(element("accounts.declare", in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(element("accounts.addBank", in: app).exists)
    }

    private func launchForAddBank(role: String?) -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrPlan", "vip", "-DincrTab", "wealth",
                         "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        if let role { arguments += ["-DincrRole", role] }
        app.launchArguments = arguments
        app.launch()
        open("wealth.accounts", in: app)
        return app
    }
}
