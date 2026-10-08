import XCTest

/// §15 PR 8 — Patrimonio: Cuentas and the mail connections (the existing screens; VIP and the Owner,
/// locked below and opening Suscripción), what is owed by debt from Plan → Deudas (every plan), and
/// no net worth figure (K-3). Android twin: `WealthUiTest`. Fixture data only.
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
            for id in ["wealth.accounts", "wealth.connections"] {
                let row = element(id, in: app)
                XCTAssertTrue(row.waitForExistence(timeout: 10), "\(context): \(id)")
                XCTAssertTrue(row.label.contains("Disponible desde VIP"), "\(context): \(id) not locked (\(row.label))")
            }
            element("wealth.accounts", in: app).tap()
            XCTAssertTrue(text("Suscripción actual", in: app).waitForExistence(timeout: 10), context)
            back(app)
            XCTAssertTrue(reveal("wealth.debts.composition", in: app).exists, "\(context): the debts")
            XCTAssertTrue(text("Tarjeta de crédito", in: app).exists)
            XCTAssertFalse(text("Patrimonio neto", in: app).exists, "K-3: no net worth figure")
            app.terminate()
        }
    }

    func testDebtsAreManagedInPlan() {
        let app = launch()
        reveal("wealth.debts.manage", in: app).tap()
        XCTAssertTrue(app.navigationBars["Deudas"].waitForExistence(timeout: 10))
    }

    func testVipOpensCuentasAndTheMailConnections() {
        let app = launch(plan: "vip")
        let accounts = element("wealth.accounts", in: app)
        XCTAssertTrue(accounts.waitForExistence(timeout: 10))
        XCTAssertFalse(accounts.label.contains("Disponible desde"))
        accounts.tap()
        XCTAssertTrue(element("accounts.bank.bac", in: app).waitForExistence(timeout: 10))
        back(app)
        element("wealth.connections", in: app).tap()
        XCTAssertTrue(element("mail.status.connected", in: app).waitForExistence(timeout: 10))
        back(app)
        XCTAssertTrue(reveal("wealth.debts.composition", in: app).exists)
        XCTAssertFalse(text("Patrimonio neto", in: app).exists, "K-3: no net worth figure")
    }

    func testTheOwnerOpensCuentasAndKeepsJarvis() {
        // The fixture seeds the connected mailbox and detected accounts for a VIP launch; the Owner reaches them by role.
        let app = launch(plan: "vip", role: "owner")
        element("wealth.accounts", in: app).tap()
        XCTAssertTrue(element("accounts.bank.bac", in: app).waitForExistence(timeout: 10))
        back(app)
        app.tabBars.buttons["Perfil"].tap()
        XCTAssertTrue(element("profile.jarvis", in: app).waitForExistence(timeout: 10))
    }
}
