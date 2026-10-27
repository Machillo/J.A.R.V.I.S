import XCTest

/// SEC-01 — the server refuses work until the current terms are accepted (`auth/legal.py`). When the
/// terms change while the app is open, the next change answers 403 `legal_acceptance_required`: the
/// app reads the identity again and shows the acceptance screen instead of leaving a bare "no
/// permission" message. Once accepted, changes run as before. Android twin: `LegalGateUiTest`.
/// Fixture data only (`-DincrLegalLapses`).
final class LegalGateUITests: XCTestCase {
    private func element(_ id: String, in app: XCUIApplication) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }

    private func tap(_ id: String, in app: XCUIApplication) {
        let target = element(id, in: app)
        XCTAssertTrue(target.waitForExistence(timeout: 10), "missing \(id)")
        target.tap()
    }

    private func payTheCard(_ app: XCUIApplication) {
        tap("home.debts", in: app)
        tap("debt.pay.31", in: app)
        let field = app.textFields["amount.field"]
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        field.tap()
        field.typeText("10.000")
        app.buttons["amount.save"].tap()
    }

    func testTermsThatChangeWhileOpenBringBackTheAcceptanceScreen() {
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrLegalLapses",
                               "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        app.launch()
        XCTAssertTrue(app.staticTexts["Resultado del mes"].waitForExistence(timeout: 10))

        payTheCard(app)
        let accept = app.buttons["legal.accept"]
        XCTAssertTrue(accept.waitForExistence(timeout: 10), "the refused change leads to the acceptance screen")
        for id in ["legal.terms", "legal.privacy"] {
            app.switches[id].coordinate(withNormalizedOffset: CGVector(dx: 0.95, dy: 0.5)).tap()
        }
        accept.tap()
        XCTAssertTrue(app.staticTexts["Resultado del mes"].waitForExistence(timeout: 10))

        payTheCard(app)
        XCTAssertTrue(element("plan.notice", in: app).waitForExistence(timeout: 10), "accepted: changes run again")
        XCTAssertFalse(accept.exists)
    }
}
