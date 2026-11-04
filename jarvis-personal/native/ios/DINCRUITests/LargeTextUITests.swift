import XCTest

/// At a large text size the totals stack instead of squeezing a word ("Resulta-do"); at the normal
/// size they stay side by side. Fixture data only.
final class LargeTextUITests: XCTestCase {
    private func launch(textSize: String?) -> XCUIApplication {
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrTab", "movements",
                         "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        if let textSize { arguments += ["-UIPreferredContentSizeCategoryName", textSize] }
        app.launchArguments = arguments
        app.launch()
        return app
    }

    private func frames(in app: XCUIApplication) -> (income: CGRect, expenses: CGRect) {
        let income = app.descendants(matching: .any)["movements.totals.income"].firstMatch
        let expenses = app.descendants(matching: .any)["movements.totals.expenses"].firstMatch
        XCTAssertTrue(income.waitForExistence(timeout: 10))
        XCTAssertTrue(expenses.waitForExistence(timeout: 10))
        return (income.frame, expenses.frame)
    }

    func testTheTotalsStayInARowAtTheNormalSize() {
        let app = launch(textSize: nil)
        let totals = frames(in: app)
        XCTAssertEqual(totals.income.minY, totals.expenses.minY, accuracy: 1)
    }

    func testTheTotalsStackAtALargeTextSize() {
        let app = launch(textSize: "UICTContentSizeCategoryAccessibilityL")
        let totals = frames(in: app)
        XCTAssertGreaterThanOrEqual(totals.expenses.minY, totals.income.maxY)
    }
}
