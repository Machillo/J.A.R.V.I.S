import XCTest

/// BIL-03 — Perfil → Suscripción's App Store panel. While the `store_billing` switch is off it only
/// says so; with it on it offers what the App Store sells to this build (nothing here: no products
/// are configured for the simulator) and keeps Restaurar and Administrar. The Owner is not a
/// subscription and has no panel. A real purchase and Restore need the App Store sandbox (physical
/// validation). Android twin: the Google Play panel (`StoreSubscriptionPanel`). Fixture data only.
final class StoreSubscriptionUITests: XCTestCase {
    private func launch(plan: String? = nil, role: String? = nil, storeBilling: Bool = false) -> XCUIApplication {
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrTab", "profile",
                         "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        if let plan { arguments += ["-DincrPlan", plan] }
        if let role { arguments += ["-DincrRole", role] }
        if storeBilling { arguments.append("-DincrStoreBilling") }
        app.launchArguments = arguments
        app.launch()
        return app
    }

    private func element(_ id: String, in app: XCUIApplication) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }

    private func openSubscription(_ app: XCUIApplication) {
        let row = element("profile.subscription", in: app)
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        row.tap()
    }

    private func reveal(_ id: String, in app: XCUIApplication) -> XCUIElement {
        let target = element(id, in: app)
        for _ in 0..<6 where !(target.exists && target.isHittable) { app.swipeUp() }
        return target
    }

    func testWhileTheSwitchIsOffThePanelOnlySaysSo() {
        let app = launch()
        openSubscription(app)
        let paused = reveal("store.paused", in: app)
        XCTAssertTrue(paused.waitForExistence(timeout: 10))
        XCTAssertTrue(paused.label.contains("App Store"), paused.label)
        XCTAssertFalse(element("store.restore", in: app).exists, "nothing to buy or restore while paused")
    }

    func testWithTheSwitchOnItOffersOnlyWhatTheStoreSells() {
        let app = launch(storeBilling: true)
        openSubscription(app)
        XCTAssertTrue(reveal("store.unavailable", in: app).waitForExistence(timeout: 15),
                      "no App Store products for this build: said in words, no price invented")
        XCTAssertFalse(app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'store.offer.'")).firstMatch.exists)
        XCTAssertTrue(element("store.restore", in: app).exists, "Restaurar compras stays available")
        XCTAssertFalse(element("store.paused", in: app).exists)
    }

    func testTheOwnerHasNoStorePanel() {
        let app = launch(plan: "vip", role: "owner", storeBilling: true)
        openSubscription(app)
        XCTAssertTrue(element("subscription.owner", in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(element("store.panel", in: app).exists)
    }
}
