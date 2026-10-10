import XCTest

/// PLN-04 — Plan → Metas y ahorro: a savings plan can be edited on iOS as on Android (name, monthly
/// amount, saved, dates, status). The form opens with the plan's figures and the list shows the
/// change. Fixture data only (plan 44, "Vacaciones").
final class SavingsPlanEditUITests: XCTestCase {
    private func element(_ id: String, in app: XCUIApplication) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }

    func testASavingsPlanIsEditedInPlace() {
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin",
                               "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        app.launch()
        let goals = element("home.goals", in: app)
        XCTAssertTrue(goals.waitForExistence(timeout: 10))
        goals.tap()

        let edit = element("plan.edit.44", in: app)
        for _ in 0..<4 where !(edit.exists && edit.isHittable) { app.swipeUp() }
        XCTAssertTrue(edit.waitForExistence(timeout: 10))
        edit.tap()

        let name = app.textFields["plan.name"]
        XCTAssertTrue(name.waitForExistence(timeout: 5))
        XCTAssertEqual(name.value as? String, "Vacaciones", "the form opens with the plan's figures")
        XCTAssertTrue(app.textFields["plan.saved"].exists, "an edit shows what is already saved")
        name.tap()
        name.clearAndType("Viaje a la playa")
        app.buttons["plan.save"].tap()

        XCTAssertTrue(element("plan.notice", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", "Viaje a la playa")).firstMatch.waitForExistence(timeout: 5))
        XCTAssertFalse(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", "Vacaciones")).firstMatch.exists)
    }
}
