import XCTest

/// "Añadir gasto" (App Shortcut, assignable to Back Tap) opens the editor of a new expense once the
/// app is signed in, and never before (`-DincrQuickAction` stands in for the system shortcut).
final class QuickActionUITests: XCTestCase {
    private func launch(skipLogin: Bool) -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-AppleLanguages", "(es)", "-AppleLocale", "es_CR",
                               "-DincrQuickAction", "new_expense"] + (skipLogin ? ["-DincrSkipLogin"] : [])
        app.launch()
        return app
    }

    func testTheShortcutOpensTheEditorOfANewExpense() {
        let app = launch(skipLogin: true)
        let save = app.buttons["editor.save"]
        XCTAssertTrue(save.waitForExistence(timeout: 10), "the editor opens")
        XCTAssertTrue(app.textFields["editor.amount"].exists)
        XCTAssertTrue(app.buttons["Gasto"].isSelected, "it starts as an expense")
        // Nothing is written until the user saves: an empty form is refused.
        save.tap()
        XCTAssertTrue(app.staticTexts["Revisá 2 campos"].waitForExistence(timeout: 2))
    }

    func testTheShortcutWaitsBehindTheSignIn() {
        let app = launch(skipLogin: false)
        XCTAssertTrue(app.buttons["login.google"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["editor.save"].exists, "no editor before signing in")
    }
}
