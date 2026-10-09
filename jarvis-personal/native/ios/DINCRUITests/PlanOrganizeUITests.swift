import XCTest

/// §15 PR 5 (option A) — Plan keeps exactly its six entries, in order. Presupuesto and Calendario
/// financiero are reached inside Tu plan del mes ("Para organizar tu mes", from Basic) and the recurring
/// income and expenses ("Movimientos recurrentes") inside Ingresos y base (every plan); back returns to
/// Plan. Metas y ahorro stays in Hoy. Android twin: `PlanOrganizeUiTest`. Fixture data only.
final class PlanOrganizeUITests: XCTestCase {
    private static let entries = ["plan.aguinaldo", "plan.strategy", "plan.debts", "plan.incomeBase", "plan.salvavidas", "plan.distribution"]

    private func launch(plan: String? = nil, role: String? = nil, tab: String = "plan") -> XCUIApplication {
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrTab", tab,
                         "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        if let plan { arguments += ["-DincrPlan", plan] }
        if let role { arguments += ["-DincrRole", role] }
        app.launchArguments = arguments
        app.launch()
        return app
    }

    private func element(_ id: String, in app: XCUIApplication) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }

    private func reveal(_ id: String, in app: XCUIApplication) -> XCUIElement {
        let target = element(id, in: app)
        for _ in 0..<6 where !(target.exists && target.isHittable) { app.swipeUp() }
        return target
    }

    private func open(_ id: String, in app: XCUIApplication) {
        let target = element(id, in: app)
        XCTAssertTrue(target.waitForExistence(timeout: 10), "missing \(id)")
        reveal(id, in: app).tap()
    }

    private func back(_ app: XCUIApplication) { app.navigationBars.buttons.element(boundBy: 0).tap() }

    func testPlanKeepsItsSixEntriesInOrder() {
        for (plan, role) in [(nil, nil), ("basic", nil), ("vip", nil), ("vip", "owner")] as [(String?, String?)] {
            let app = launch(plan: plan, role: role)
            XCTAssertTrue(element(Self.entries[0], in: app).waitForExistence(timeout: 10))
            let frames = Self.entries.map { element($0, in: app).frame.minY }
            XCTAssertEqual(frames, frames.sorted(), "\(role ?? plan ?? "free"): order")
            for id in ["plan.budget", "plan.calendar", "plan.recurring", "plan.goals"] { XCTAssertFalse(element(id, in: app).exists, id) }
            app.terminate()
        }
    }

    func testBasicOrganizesTheMonthAndReturnsToThePlan() {
        let app = launch(plan: "basic")
        open("plan.strategy", in: app)
        XCTAssertTrue(app.navigationBars["Tu plan del mes"].waitForExistence(timeout: 10))
        let budget = reveal("plan.month.budget", in: app)
        XCTAssertTrue(budget.exists)
        XCTAssertFalse(budget.label.contains("Disponible desde"))
        budget.tap()
        XCTAssertTrue(app.navigationBars["Presupuesto"].waitForExistence(timeout: 10))
        back(app)
        XCTAssertTrue(app.navigationBars["Tu plan del mes"].waitForExistence(timeout: 10))
        reveal("plan.month.calendar", in: app).tap()
        XCTAssertTrue(app.navigationBars["Calendario"].waitForExistence(timeout: 10))
        back(app)
        XCTAssertTrue(app.navigationBars["Tu plan del mes"].waitForExistence(timeout: 10))
        back(app)
        XCTAssertTrue(element("plan.incomeBase", in: app).waitForExistence(timeout: 10), "back in Plan")
    }

    func testFreeKeepsTheMonthLockedAndOpensItsRecurringTransactions() {
        let app = launch()
        open("plan.strategy", in: app)
        XCTAssertTrue(app.staticTexts["Suscripción actual"].waitForExistence(timeout: 10), "Tu plan del mes stays Basic")
        XCTAssertFalse(element("plan.month.budget", in: app).exists)
        back(app)
        open("plan.incomeBase", in: app)
        open("incomeBase.recurring", in: app)
        XCTAssertTrue(app.navigationBars["Movimientos recurrentes"].waitForExistence(timeout: 10))
        back(app)
        XCTAssertTrue(app.navigationBars["Ingresos y base"].waitForExistence(timeout: 10))
    }

    func testVipAndOwnerReachEveryAccessAndTheOwnerKeepsJarvis() {
        for (plan, role) in [("vip", nil), ("vip", "owner")] as [(String?, String?)] {
            let app = launch(plan: plan, role: role)
            open("plan.strategy", in: app)
            XCTAssertTrue(reveal("plan.month.budget", in: app).exists, role ?? "vip")
            XCTAssertTrue(reveal("plan.month.calendar", in: app).exists, role ?? "vip")
            back(app)
            open("plan.incomeBase", in: app)
            XCTAssertTrue(reveal("incomeBase.recurring", in: app).exists, role ?? "vip")
            back(app)
            app.tabBars.buttons["Perfil"].tap()
            XCTAssertEqual(element("profile.jarvis", in: app).waitForExistence(timeout: 5), role == "owner")
            app.terminate()
        }
    }

    func testMetasYAhorroStaysInHoy() {
        let app = launch(tab: "home")
        XCTAssertTrue(element("home.goals", in: app).waitForExistence(timeout: 10))
    }
}
