import XCTest

/// PR 4 (P6.4) — Perfil never hides a row the subscription does not include: Correos and Cuentas are
/// locked below VIP, Presupuesto and Calendario below Basic; a locked row opens Suscripción. VIP and
/// the Owner (by role) open every row, and the Owner keeps JARVIS. Android twin: `LockedRowsUiTest`.
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

    func testFreeSeesEveryRowLockedAndALockedRowOpensSuscripcion() {
        let app = launch()
        assertRows(app, locked: ["profile.mail": "Disponible desde VIP", "profile.accounts": "Disponible desde VIP",
                                 "profile.budget": "Disponible desde Basic", "profile.calendar": "Disponible desde Basic"],
                   open: ["profile.recurring"], context: "free")
        row("profile.budget", in: app).tap()
        XCTAssertTrue(app.staticTexts["Suscripción actual"].waitForExistence(timeout: 10))
        app.navigationBars.buttons.element(boundBy: 0).tap()
        row("profile.mail", in: app).tap()
        XCTAssertTrue(app.staticTexts["Suscripción actual"].waitForExistence(timeout: 10))
    }

    func testBasicHasBudgetAndCalendarAndSeesMailLocked() {
        let app = launch(plan: "basic")
        assertRows(app, locked: ["profile.mail": "Disponible desde VIP", "profile.accounts": "Disponible desde VIP"],
                   open: ["profile.budget", "profile.calendar", "profile.recurring"], context: "basic")
        row("profile.accounts", in: app).tap()
        XCTAssertTrue(app.staticTexts["Suscripción actual"].waitForExistence(timeout: 10))
    }

    func testVipAndOwnerOpenEveryRowAndTheOwnerKeepsJarvis() {
        for (plan, role) in [("vip", nil), (nil, "owner")] as [(String?, String?)] {
            let app = launch(plan: plan, role: role)
            assertRows(app, locked: [:], open: ["profile.mail", "profile.accounts", "profile.budget", "profile.calendar", "profile.recurring"],
                       context: role ?? "vip")
            XCTAssertEqual(row("profile.jarvis", in: app).exists, role == "owner")
            app.terminate()
        }
    }

    func testTheLockedRowSpeaksEnglish() {
        let app = launch(english: true)
        XCTAssertTrue(row("profile.budget", in: app).label.contains("Available from Basic"))
        XCTAssertTrue(row("profile.mail", in: app).label.contains("Available from VIP"))
    }
}
