import XCTest

/// GO-1 — Hoy → Metas y ahorro: each goal says what it takes in plain words. A goal with a date
/// says how much per month; one without asks for a date; VIP and the Owner also see how long it takes
/// with what is left in a normal month. Android twin: `GoalPlanUiTest`. Fixture data only.
@MainActor
final class GoalPlanUITests: XCTestCase {
    private func element(_ id: String, in app: XCUIApplication) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }
    private func text(_ content: String, in app: XCUIApplication) -> XCUIElement {
        app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", content)).firstMatch
    }

    private func openGoals(plan: String?) -> XCUIApplication {
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        if let plan { arguments += ["-DincrPlan", plan] }
        app.launchArguments = arguments
        app.launch()
        let goals = element("home.goals", in: app)
        XCTAssertTrue(goals.waitForExistence(timeout: 10))
        goals.tap()
        return app
    }

    func testEveryPlanSeesWhatEachGoalTakes() {
        let app = openGoals(plan: nil)
        XCTAssertTrue(text("necesitás", in: app).waitForExistence(timeout: 10), "the dated goal says how much per month")
        XCTAssertTrue(text("Poné una fecha", in: app).exists, "the goal without a date asks for one")
        XCTAssertFalse(text("en un mes normal", in: app).exists, "Free has no normal month")
    }

    func testVipAlsoSeesHowLongWithItsNormalMonth() {
        let app = openGoals(plan: "vip")
        XCTAssertTrue(text("Con lo que te sobra en un mes normal", in: app).waitForExistence(timeout: 10))
    }
}
