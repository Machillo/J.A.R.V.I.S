import XCTest

/// Hoy (UX-6) on the fixture backend: four blocks for every public plan — Estado de hoy, Para atender
/// (VIP only: Free and Basic have no source), Qué sigue (one thing), Accesos rápidos (the same four) —
/// and the Owner's JARVIS space before them. Synthetic data only. Android twin: `HomeTodayUiTest`.
@MainActor
final class HomeTodayUITests: XCTestCase {
    private func launch(plan: String?, role: String? = nil, scenario: String = "populated") -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", scenario, "-DincrSkipLogin",
                         "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        if let plan { arguments += ["-DincrPlan", plan] }
        if let role { arguments += ["-DincrRole", role] }
        app.launchArguments = arguments
        app.launch()
        return app
    }

    private func element(_ identifier: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any)[identifier].firstMatch
    }

    private func text(_ content: String, in app: XCUIApplication) -> XCUIElement {
        app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", content)).firstMatch
    }

    @discardableResult
    private func reveal(_ identifier: String, in app: XCUIApplication) -> XCUIElement {
        let target = element(identifier, in: app)
        XCTAssertTrue(target.waitForExistence(timeout: 10), "missing \(identifier)")
        for _ in 0..<8 where !target.isHittable { app.swipeUp() }
        XCTAssertTrue(target.isHittable, "\(identifier) is not reachable")
        return target
    }

    /// What no public Hoy shows as a main block any more.
    private func assertNoRetiredBlocks(_ app: XCUIApplication, _ plan: String) {
        for retired in ["Salud financiera", "/100", "Tu hoja de ruta", "Tu plan de acción", "Patrimonio neto", "En 6 meses",
                        "Ingresos y gastos", "En qué se va el dinero"] {
            XCTAssertFalse(text(retired, in: app).exists, "\(plan): \(retired)")
        }
    }

    private func assertQuickAccess(_ app: XCUIApplication, prefix: String = "home") {
        for id in ["\(prefix).shortcut.registerMovement", "\(prefix).shortcut.movements", "\(prefix).debts", "\(prefix).goals"] {
            XCTAssertTrue(element(id, in: app).exists, id)
        }
    }

    func testFreeShowsRealFactsAndNoIntelligence() {
        let app = launch(plan: nil)
        XCTAssertTrue(element("home.status", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Resultado del mes", in: app).exists)
        XCTAssertTrue(element("home.status.amount", in: app).exists)
        XCTAssertFalse(text("Podés gastar con tranquilidad", in: app).exists)
        XCTAssertFalse(element("home.attention", in: app).exists, "Free has no source for Para atender")
        XCTAssertFalse(element("home.status.budget", in: app).exists)
        reveal("home.next", in: app)
        reveal("home.shortcuts", in: app)
        assertQuickAccess(app)
        assertNoRetiredBlocks(app, "free")
    }

    func testFreeWithoutIncomeSaysWhatIsMissingAndOpensTheRealIncomeFlow() {
        let app = launch(plan: nil, scenario: "empty")
        XCTAssertTrue(element("home.status.unknown", in: app).waitForExistence(timeout: 10), "unknown, never ₡0")
        XCTAssertFalse(element("home.status.amount", in: app).exists)
        reveal("home.status.help", in: app).tap()
        reveal("home.status.missing.income", in: app).tap()
        // The existing movement editor, opened as an income (salary / pay stub categories).
        XCTAssertTrue(app.buttons["editor.save"].waitForExistence(timeout: 5))
        XCTAssertTrue(text("Salario", in: app).exists || app.buttons["Salario"].exists)
    }

    func testBasicAddsItsBudgetWithoutVipIntelligence() {
        let app = launch(plan: "basic")
        XCTAssertTrue(element("home.status", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(element("home.status.budget", in: app).exists, "the user's own budget left")
        XCTAssertTrue(element("home.status.pending", in: app).exists, "this month's pending payments")
        XCTAssertFalse(text("Podés gastar con tranquilidad", in: app).exists)
        XCTAssertFalse(element("home.attention", in: app).exists)
        reveal("home.next", in: app)
        assertQuickAccess(app)
        assertNoRetiredBlocks(app, "basic")
    }

    func testVipShowsSafeToSpendOneRecommendationAndAttention() {
        let app = launch(plan: "vip")
        XCTAssertTrue(element("home.status.amount", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Podés gastar con tranquilidad", in: app).exists)
        XCTAssertTrue(element("home.attention", in: app).exists)
        reveal("home.next", in: app)
        XCTAssertTrue(text("Tu prioridad es bajar la tarjeta", in: app).exists, "the director's one recommendation")
        reveal("home.next.action", in: app).tap()
        XCTAssertTrue(app.navigationBars["Tu plan del mes"].waitForExistence(timeout: 10), "the detail lives in Plan → Tu plan del mes")
        app.navigationBars.buttons.element(boundBy: 0).tap()
        assertQuickAccess(app)
        assertNoRetiredBlocks(app, "vip")
    }

    func testOwnerHasJarvisFirstThenTheFinancialBlocks() {
        let app = launch(plan: "vip", role: "owner")
        XCTAssertTrue(element("owner.home", in: app).waitForExistence(timeout: 10))
        let jarvis = element("owner.home.jarvis.chat", in: app)
        let status = element("owner.home.status", in: app)
        XCTAssertTrue(jarvis.waitForExistence(timeout: 10) && status.waitForExistence(timeout: 10))
        XCTAssertLessThan(jarvis.frame.minY, status.frame.minY, "JARVIS comes first")
        XCTAssertTrue(element("owner.home.jarvis.mark", in: app).exists)
        XCTAssertTrue(element("owner.home.jarvis.agenda", in: app).exists)
        XCTAssertTrue(element("owner.home.jarvis.hub", in: app).exists)
        reveal("owner.home.shortcuts", in: app)
        assertQuickAccess(app, prefix: "owner.home")
        XCTAssertFalse(element("home.today", in: app).exists, "the Owner never gets the public Hoy")
    }
}
