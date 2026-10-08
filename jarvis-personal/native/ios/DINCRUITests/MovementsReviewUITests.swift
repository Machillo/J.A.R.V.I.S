import XCTest

/// §15 PR 6 — Movimientos → Por revisar: VIP and the Owner review the detected bank notices in the
/// existing Email Monitor (the same screen as Perfil's). A pending notice is not a movement until it is
/// confirmed; then it appears in the list. Free and Basic see the entry locked and it opens Suscripción.
/// The five tabs and Análisis stay. Android twin: `MovementsReviewUiTest`. Fixture data only.
final class MovementsReviewUITests: XCTestCase {
    private func launch(plan: String? = nil, role: String? = nil) -> XCUIApplication {
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrTab", "movements",
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

    private func text(_ content: String, in app: XCUIApplication) -> XCUIElement {
        app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", content)).firstMatch
    }

    func testFreeAndBasicSeePorRevisarLockedAndItOpensSuscripcion() {
        for plan in [nil, "basic"] as [String?] {
            let app = launch(plan: plan)
            let entry = element("movements.review", in: app)
            XCTAssertTrue(entry.waitForExistence(timeout: 10), plan ?? "free")
            XCTAssertTrue(entry.label.contains("Disponible desde VIP"), "\(plan ?? "free"): \(entry.label)")
            XCTAssertTrue(element("movements.analysis", in: app).exists)
            entry.tap()
            XCTAssertTrue(text("Suscripción actual", in: app).waitForExistence(timeout: 10), plan ?? "free")
            XCTAssertFalse(element("mail.accept.21", in: app).exists)
            app.terminate()
        }
    }

    func testVipReviewsANoticeAndOnlyThenItIsAMovement() {
        let app = launch(plan: "vip")
        XCTAssertTrue(element("movements.analysis", in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(element("movements.review", in: app).label.contains("Disponible desde"))
        XCTAssertFalse(text("Compra en supermercado", in: app).exists, "a pending notice is not a movement")
        open("movements.review", in: app)
        open("mail.accept.21", in: app)
        XCTAssertTrue(element("mail.notice", in: app).waitForExistence(timeout: 10))
        app.navigationBars.buttons.element(boundBy: 0).tap()
        XCTAssertTrue(text("Compra en supermercado", in: app).waitForExistence(timeout: 10), "the confirmed notice is now a movement")
        XCTAssertEqual(app.tabBars.buttons.allElementsBoundByIndex.map { $0.label }, ["Hoy", "Movimientos", "Plan", "Patrimonio", "Perfil"])
    }

    func testTheOwnerReviewsToo() {
        // The fixture seeds the connected mailbox for a VIP launch; the Owner reaches it by role.
        let app = launch(plan: "vip", role: "owner")
        open("movements.review", in: app)
        XCTAssertTrue(element("mail.accept.21", in: app).waitForExistence(timeout: 10))
        app.navigationBars.buttons.element(boundBy: 0).tap()
        app.tabBars.buttons["Perfil"].tap()
        XCTAssertTrue(element("profile.jarvis", in: app).waitForExistence(timeout: 10))
    }
}
