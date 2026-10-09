import XCTest

/// PR 4 (P6.4) — locked rows instead of hidden ones. §15 PR 10 moved every locked function out of Perfil:
/// Correos and Cuentas to Patrimonio (`WealthUITests`), Presupuesto and Calendario to Plan → Tu plan del
/// mes (`PlanOrganizeUITests`), Movimientos recurrentes to Plan → Ingresos y base. Perfil keeps none.
/// Android twin: `LockedRowsUiTest`.
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

    /// §15 PR 10 (option A): Perfil keeps no locked rows: Presupuesto and Calendario are locked inside Plan →
    /// Tu plan del mes (`PlanOrganizeUITests`), Correos and Cuentas in Patrimonio (`WealthUITests`).
    func testPerfilHasNoLockedRowsLeftAndTheOwnerKeepsJarvis() {
        for (plan, role) in [(nil, nil), ("basic", nil), ("vip", nil), (nil, "owner")] as [(String?, String?)] {
            let app = launch(plan: plan, role: role)
            XCTAssertTrue(row("profile.subscription", in: app).waitForExistence(timeout: 10))
            XCTAssertFalse(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", "Disponible desde")).firstMatch.exists,
                           role ?? plan ?? "free")
            for id in ["profile.budget", "profile.calendar", "profile.recurring", "profile.mail", "profile.accounts"] {
                XCTAssertFalse(app.descendants(matching: .any)[id].exists, "\(role ?? plan ?? "free"): \(id)")
            }
            XCTAssertEqual(row("profile.jarvis", in: app).exists, role == "owner")
            app.terminate()
        }
    }
}
