import XCTest

/// PR 4 (P6.4) — locked rows instead of hidden ones. §15 PR 10 moved every locked function out of Perfil:
/// Correos and Cuentas to Patrimonio (`WealthUITests`), Presupuesto and Calendario to Plan → Tu plan del
/// mes (`PlanOrganizeUITests`), Movimientos recurrentes to Plan → Ingresos y base. Perfil keeps none, except
/// Atajos de iPhone (SC-1, iOS only; locked below VIP, `ShortcutsSettingsUITests`).
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
    /// Tu plan del mes (`PlanOrganizeUITests`), Cuentas in Patrimonio (`WealthUITests`); the mail connections in Perfil (WE-1, Owner only). SC-1: the
    /// only locked row Perfil adds back is Atajos de iPhone (`profile.shortcuts`), a Perfil setting by nature.
    func testPerfilHasNoLockedRowsLeftAndTheOwnerKeepsJarvis() {
        for (plan, role) in [(nil, nil), ("basic", nil), ("vip", nil), (nil, "owner")] as [(String?, String?)] {
            let app = launch(plan: plan, role: role)
            XCTAssertTrue(row("profile.subscription", in: app).waitForExistence(timeout: 10))
            // Any "Disponible desde" label must belong to the Atajos de iPhone row (the row or a text inside it).
            let shortcuts = row("profile.shortcuts", in: app)
            let lockedLabels = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", "Disponible desde")).allElementsBoundByIndex
            for element in lockedLabels {
                XCTAssertTrue(shortcuts.exists && shortcuts.frame.contains(element.frame),
                              "\(role ?? plan ?? "free"): locked row outside Atajos de iPhone (\(element.identifier))")
            }
            for id in ["profile.budget", "profile.calendar", "profile.recurring", "profile.accounts"] {
                XCTAssertFalse(app.descendants(matching: .any)[id].exists, "\(role ?? plan ?? "free"): \(id)")
            }
            // WE-1: the mail connections are back in Perfil, the Owner's alone (never shown locked).
            XCTAssertEqual(app.descendants(matching: .any)["profile.mail"].exists, role == "owner", "\(role ?? plan ?? "free"): profile.mail")
            XCTAssertEqual(row("profile.jarvis", in: app).exists, role == "owner")
            // NT-1: every plan can turn the reminders on the phone on or off.
            XCTAssertTrue(app.descendants(matching: .any)["profile.reminders"].exists, "\(role ?? plan ?? "free"): Recordatorios")
            app.terminate()
        }
    }
}
