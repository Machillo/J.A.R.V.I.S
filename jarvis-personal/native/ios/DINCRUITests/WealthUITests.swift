import XCTest

/// §15 PR 8 — Patrimonio: Cuentas and the mail connections (the existing screens; VIP and the Owner,
/// locked below and opening Suscripción), what is owed by debt from Plan → Deudas (every plan), and
/// the net worth on top for VIP and the Owner (WE-2). Android twin: `WealthUiTest`. Fixture data only.
final class WealthUITests: XCTestCase {
    private func launch(plan: String? = nil, role: String? = nil) -> XCUIApplication {
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrTab", "wealth",
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
        if !target.waitForExistence(timeout: 10) || !target.isHittable { app.swipeUp() }
        return target
    }

    private func text(_ content: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", content)).firstMatch
    }

    private func back(_ app: XCUIApplication) { app.navigationBars.buttons.element(boundBy: 0).tap() }

    func testFreeAndBasicSeeTheirDebtsAndCuentasLocked() {
        for plan in [nil, "basic"] as [String?] {
            let app = launch(plan: plan)
            let context = plan ?? "free"
            let row = element("wealth.accounts", in: app)
            XCTAssertTrue(row.waitForExistence(timeout: 10), "\(context): wealth.accounts")
            XCTAssertTrue(row.label.contains("Disponible desde VIP"), "\(context): wealth.accounts not locked (\(row.label))")
            // Conexiones de correo is the Owner's alone during the launch: not even shown locked.
            XCTAssertFalse(element("wealth.connections", in: app).exists, "\(context): no Conexiones de correo")
            element("wealth.accounts", in: app).tap()
            XCTAssertTrue(text("Suscripción actual", in: app).waitForExistence(timeout: 10), context)
            back(app)
            XCTAssertTrue(reveal("wealth.debts.composition", in: app).exists, "\(context): the debts")
            XCTAssertTrue(text("Tarjeta de crédito", in: app).exists)
            // WE-2: the net worth is VIP's: shown locked, with no figure.
            XCTAssertTrue(element("wealth.netWorth", in: app).label.contains("Disponible desde VIP"), context)
            XCTAssertFalse(element("wealth.netWorth.amount", in: app).exists, context)
            app.terminate()
        }
    }

    func testDebtsAreManagedInPlan() {
        let app = launch()
        reveal("wealth.debts.manage", in: app).tap()
        XCTAssertTrue(app.navigationBars["Deudas"].waitForExistence(timeout: 10))
    }

    func testVipOpensCuentasButNotTheMailConnections() {
        let app = launch(plan: "vip")
        let accounts = reveal("wealth.accounts", in: app)
        XCTAssertTrue(accounts.waitForExistence(timeout: 10))
        XCTAssertFalse(accounts.label.contains("Disponible desde"))
        accounts.tap()
        XCTAssertTrue(element("accounts.bank.bac", in: app).waitForExistence(timeout: 10))
        back(app)
        XCTAssertFalse(element("wealth.connections", in: app).exists, "no Conexiones de correo for a VIP")
        XCTAssertTrue(reveal("wealth.debts.composition", in: app).exists)
    }

    func testTheOwnerOpensCuentasAndKeepsJarvis() {
        // The fixture seeds the connected mailbox and detected accounts for a VIP launch; the Owner reaches them by role.
        let app = launch(plan: "vip", role: "owner")
        element("wealth.connections", in: app).tap()
        XCTAssertTrue(element("mail.status.connected", in: app).waitForExistence(timeout: 10))
        back(app)
        element("wealth.accounts", in: app).tap()
        XCTAssertTrue(element("accounts.bank.bac", in: app).waitForExistence(timeout: 10))
        back(app)
        app.tabBars.buttons["Perfil"].tap()
        XCTAssertTrue(element("profile.jarvis", in: app).waitForExistence(timeout: 10))
    }

    /// WE-2: VIP and the Owner see what they have minus what they owe, on top of Patrimonio.
    func testVipAndTheOwnerSeeTheirNetWorth() {
        for role in [nil, "owner"] as [String?] {
            let app = launch(plan: "vip", role: role)
            XCTAssertTrue(element("wealth.netWorth.amount", in: app).waitForExistence(timeout: 10), role ?? "vip")
            XCTAssertTrue(element("wealth.assets", in: app).exists && element("wealth.liabilities", in: app).exists)
            XCTAssertTrue(text("Salvavidas", in: app).exists && text("Fondo de inversión", in: app).exists)
            app.terminate()
        }
    }
}
