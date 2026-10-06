import XCTest

/// "Para atender" (UX-5) on the fixture backend: VIP's populated command center has four matters (a
/// high one, two medium alerts and the pending mail notices, which the backend also raises as an
/// alert), so Hoy shows three and "Ver todas". Free and Basic have no section; the Owner's Today shares
/// it (OwnerExperienceUITests). Synthetic data only.
@MainActor
final class AttentionUITests: XCTestCase {
    private func launch(plan: String?, role: String? = nil) -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin",
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

    private func texts(_ content: String, in app: XCUIApplication) -> XCUIElementQuery {
        app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", content))
    }

    @discardableResult
    private func reveal(_ identifier: String, in app: XCUIApplication) -> XCUIElement {
        let target = element(identifier, in: app)
        XCTAssertTrue(target.waitForExistence(timeout: 10), "missing \(identifier)")
        for _ in 0..<8 where !target.isHittable { app.swipeUp() }
        XCTAssertTrue(target.isHittable, "\(identifier) is not reachable")
        return target
    }

    func testVipTodayShowsThreeMattersInOrderAndSeeAll() {
        let app = launch(plan: "vip")
        XCTAssertTrue(element("home.status.amount", in: app).waitForExistence(timeout: 10))
        reveal("home.attention.all", in: app)
        let high = texts("Reserva menor a un mes", in: app).firstMatch
        let medium = texts("Pago de tarjeta en 5 días", in: app).firstMatch
        XCTAssertTrue(high.exists && medium.exists)
        XCTAssertLessThan(high.frame.minY, medium.frame.minY, "high before medium")
        XCTAssertTrue(texts("Recurrente con variación", in: app).firstMatch.exists)
        // The fourth (the mail notices, last among the medium ones) waits behind "Ver todas".
        XCTAssertFalse(texts("Movimientos por revisar", in: app).firstMatch.exists)
        XCTAssertFalse(element("home.attention.link.review", in: app).exists)
        // The old separate mail row and "Alertas" list are gone: one section.
        XCTAssertFalse(app.staticTexts["Alertas"].exists)
        XCTAssertFalse(app.staticTexts["Avisos del correo por revisar"].exists)
        // A command-center action is free text: shown as words, never a link.
        XCTAssertTrue(texts("Revisá la deuda", in: app).firstMatch.exists)
        XCTAssertFalse(element("home.attention.link.debts", in: app).exists)
    }

    func testSeeAllListsEveryMatterOnceAndOpensTheMailReview() {
        let app = launch(plan: "vip")
        reveal("home.attention.all", in: app).tap()
        XCTAssertTrue(element("attention.list", in: app).waitForExistence(timeout: 10))
        let review = reveal("attention.link.review", in: app)
        // The backend's pending-review alert and the mail count are one item: four matters in all.
        let items = app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH %@", "attention.item."))
        XCTAssertEqual(Set((0..<items.count).map { items.element(boundBy: $0).identifier }), ["attention.item.center", "attention.item.review"])
        XCTAssertEqual(app.descendants(matching: .any).matching(identifier: "attention.item.review").count, 1)
        XCTAssertEqual(app.descendants(matching: .any).matching(identifier: "attention.item.center").count, 3)
        XCTAssertTrue(texts("Reserva menor a un mes", in: app).firstMatch.exists)
        // The advisor answered (no earlier observation yet): no technical problem, no invented change.
        XCTAssertFalse(element("attention.advisor.unavailable", in: app).exists)
        XCTAssertFalse(element("attention.item.advisor", in: app).exists)
        XCTAssertFalse(element("attention.none", in: app).exists)
        review.tap()
        XCTAssertTrue(texts("Por revisar", in: app).firstMatch.waitForExistence(timeout: 10), "the Email Monitor")
    }

    func testFreeAndBasicHaveNoAttentionSection() {
        for plan in [nil, "basic"] as [String?] {
            let app = launch(plan: plan)
            let today = element("home.status", in: app)
            XCTAssertTrue(today.waitForExistence(timeout: 10), plan ?? "free")
            XCTAssertFalse(element("home.attention", in: app).exists, plan ?? "free")
            XCTAssertFalse(texts("Nada pendiente", in: app).firstMatch.exists, plan ?? "free")
            app.terminate()
        }
    }

    func testOwnerTodaySharesTheSectionWithoutAFalseAllClear() {
        let app = launch(plan: "vip", role: "owner")
        XCTAssertTrue(element("owner.home", in: app).waitForExistence(timeout: 10))
        reveal("owner.home.attention.all", in: app)
        XCTAssertFalse(texts("Nada pendiente", in: app).firstMatch.exists)
        let high = texts("Reserva menor a un mes", in: app).firstMatch
        let medium = texts("Pago de tarjeta en 5 días", in: app).firstMatch
        XCTAssertLessThan(high.frame.minY, medium.frame.minY, "high before medium")
    }
}
