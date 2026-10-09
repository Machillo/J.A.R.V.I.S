import XCTest

/// PR 4 (P6.4) — Perfil never hides a row the subscription does not include: Presupuesto and
/// Calendario are locked below Basic and open Suscripción. VIP and the Owner (by role) open every row,
/// and the Owner keeps JARVIS. §15 PR 10: Correos and Cuentas left Perfil for Patrimonio (locked there
/// below VIP: `WealthUITests`). Android twin: `LockedRowsUiTest`.
final class LockedRowsUITests: XCTestCase {
    private func launch(plan: String? = nil, role: String? = nil, english: Bool = false) -> XCUIApplication {
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrTab", "profile"]
        arguments += english ? ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"] : ["-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        if let plan { arguments += ["-DincrPlan", plan] }
        if let role { arguments += ["-DincrRole", role] }
        app.launchArguments = arguments
        app.launch()
        return app
    }

    private func row(_ id: String, in app: XCUIApplication) -> XCUIElement {
        let element = app.descendants(matching: .any)[id].firstMatch
        if !element.waitForExistence(timeout: 10) { app.swipeUp() }
        return element
    }

    private func assertRows(_ app: XCUIApplication, locked: [String: String], open: [String], context: String) {
        for (id, label) in locked {
            let element = row(id, in: app)
            XCTAssertTrue(element.waitForExistence(timeout: 5), "\(context): \(id) missing")
            XCTAssertTrue(element.label.contains(label), "\(context): \(id) not locked (\(element.label))")
        }
        for id in open {
            let element = row(id, in: app)
            XCTAssertTrue(element.waitForExistence(timeout: 5), "\(context): \(id) missing")
            XCTAssertFalse(element.label.contains("Disponible desde"), "\(context): \(id) shown locked")
        }
    }

    func testFreeSeesBudgetAndCalendarLockedAndALockedRowOpensSuscripcion() {
        let app = launch()
        assertRows(app, locked: ["profile.budget": "Disponible desde Basic", "profile.calendar": "Disponible desde Basic"],
                   open: ["profile.recurring"], context: "free")
        row("profile.budget", in: app).tap()
        XCTAssertTrue(app.staticTexts["Suscripción actual"].waitForExistence(timeout: 10))
    }

    func testBasicOpensBudgetAndCalendar() {
        let app = launch(plan: "basic")
        assertRows(app, locked: [:], open: ["profile.budget", "profile.calendar", "profile.recurring"], context: "basic")
    }

    func testVipAndOwnerOpenEveryRowAndTheOwnerKeepsJarvis() {
        for (plan, role) in [("vip", nil), (nil, "owner")] as [(String?, String?)] {
            let app = launch(plan: plan, role: role)
            assertRows(app, locked: [:], open: ["profile.budget", "profile.calendar", "profile.recurring"], context: role ?? "vip")
            XCTAssertEqual(row("profile.jarvis", in: app).exists, role == "owner")
            app.terminate()
        }
    }

    /// §15 PR 10: Correos and Cuentas live in Patrimonio (and Movimientos → Por revisar) for every plan;
    /// Perfil no longer lists them.
    func testPerfilNoLongerListsCorreosOrCuentas() {
        for (plan, role) in [(nil, nil), ("basic", nil), ("vip", nil), ("vip", "owner")] as [(String?, String?)] {
            let app = launch(plan: plan, role: role)
            XCTAssertTrue(row("profile.subscription", in: app).waitForExistence(timeout: 10))
            XCTAssertFalse(app.descendants(matching: .any)["profile.mail"].exists, role ?? plan ?? "free")
            XCTAssertFalse(app.descendants(matching: .any)["profile.accounts"].exists, role ?? plan ?? "free")
            app.terminate()
        }
    }

    func testTheLockedRowSpeaksEnglish() {
        let app = launch(english: true)
        XCTAssertTrue(row("profile.budget", in: app).label.contains("Available from Basic"))
    }
}
