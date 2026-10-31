import XCTest

/// FA-1 — Movimientos → Análisis → Análisis financiero for VIP and the Owner: their own months in
/// plain words (a normal month, how much is saved and goes to debts, the months side by side, what is
/// above normal this month). Free and Basic see the row locked; it opens Suscripción. JARVIS →
/// Análisis financiero keeps the Owner's full historical analysis. Android twin:
/// `OwnerAnalysisPlacementUiTest`. Fixture data only.
final class OwnerAnalysisPlacementUITests: XCTestCase {
    private func launch(plan: String? = nil, role: String? = nil, tab: String) -> XCUIApplication {
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

    private func open(_ id: String, in app: XCUIApplication) {
        let target = element(id, in: app)
        XCTAssertTrue(target.waitForExistence(timeout: 10), "missing \(id)")
        if !target.isHittable { app.swipeUp() }
        target.tap()
    }

    private func contains(_ text: String, in app: XCUIApplication) -> Bool {
        app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", text)).count > 0
    }

    /// Scrolls down until `id` exists (the screen is long), at most a few times.
    private func reveal(_ id: String, in app: XCUIApplication) -> Bool {
        for _ in 0..<6 {
            if element(id, in: app).exists { return true }
            app.swipeUp()
        }
        return element(id, in: app).exists
    }

    func testFreeAndBasicSeeTheAnalysisLockedAndItOpensSuscripcion() {
        for plan in [nil, "basic"] as [String?] {
            let app = launch(plan: plan, tab: "movements")
            open("movements.analysis", in: app)
            let entry = element("analysis.financial", in: app)
            XCTAssertTrue(entry.waitForExistence(timeout: 10), plan ?? "free")
            XCTAssertTrue(entry.label.contains("Disponible desde VIP"), "\(plan ?? "free"): \(entry.label)")
            entry.tap()
            XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Suscripción actual")).firstMatch.waitForExistence(timeout: 10), plan ?? "free")
            app.terminate()
        }
    }

    func testVipAndTheOwnerReadTheirNumbersInPlainWords() {
        for role in [nil, "owner"] as [String?] {
            let who = role ?? "vip"
            let app = launch(plan: "vip", role: role, tab: "movements")
            open("movements.analysis", in: app)
            open("analysis.financial", in: app)
            XCTAssertTrue(app.navigationBars["Análisis financiero"].waitForExistence(timeout: 10), who)
            XCTAssertTrue(element("analysis.financial.left", in: app).waitForExistence(timeout: 10), who)
            XCTAssertTrue(contains("En un mes normal te sobran", in: app), who)
            XCTAssertTrue(reveal("analysis.financial.saved", in: app) && contains("Guardás 10 de cada 100 que entran.", in: app), who)
            XCTAssertTrue(reveal("analysis.financial.debts", in: app), who)
            XCTAssertTrue(reveal("analysis.financial.months", in: app), who)
            XCTAssertTrue(reveal("analysis.financial.rises", in: app) && contains("Comida:", in: app), who)
            // Not the Owner's historical analysis: no score and no net worth here.
            for hidden in ["jarvis.analysis.health", "jarvis.analysis.networth"] { XCTAssertFalse(element(hidden, in: app).exists, hidden) }
            XCTAssertEqual(app.tabBars.buttons.allElementsBoundByIndex.map { $0.label }, ["Hoy", "Movimientos", "Plan", "Patrimonio", "Perfil"])
            app.terminate()
        }
    }

    func testJarvisKeepsTheFullAnalysis() {
        let app = launch(plan: "vip", role: "owner", tab: "profile")
        open("profile.jarvis", in: app)
        open("jarvis.section.analysis", in: app)
        XCTAssertTrue(element("jarvis.analysis.health", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(contains("/100", in: app))
        XCTAssertTrue(reveal("jarvis.analysis.networth", in: app))
    }
}
