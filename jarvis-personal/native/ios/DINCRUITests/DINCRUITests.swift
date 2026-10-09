import XCTest

/// End-to-end flows on synthetic fixture data (no backend, no real account).
/// XCUIApplication is main-actor isolated (Swift 6 language mode), so the tests are too.
@MainActor
final class DINCRUITests: XCTestCase {
    private func launch(_ scenario: String = "populated", skipLogin: Bool = true, extra: [String] = []) -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", scenario, "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"] + (skipLogin ? ["-DincrSkipLogin"] : []) + extra
        app.launch()
        return app
    }

    func testLoginLeadsToHome() {
        let app = launch(skipLogin: false)
        let google = app.buttons["login.google"]
        XCTAssertTrue(google.waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["login.apple"].exists)
        google.tap()
        XCTAssertTrue(app.staticTexts["Resultado del mes"].waitForExistence(timeout: 5))
    }

    func testHomeShowsItsFourBlocks() {
        // UX-6: Estado de hoy, Qué sigue and Accesos rápidos (Free has no "Para atender" source).
        let app = launch()
        XCTAssertTrue(app.staticTexts["Resultado del mes"].waitForExistence(timeout: 5))
        for id in ["home.status", "home.next", "home.shortcuts"] {
            XCTAssertTrue(app.descendants(matching: .any)[id].exists, id)
        }
        // The month's analysis lives in Movimientos, not on Hoy.
        XCTAssertFalse(app.staticTexts["Ingresos y gastos"].exists)
        XCTAssertFalse(app.staticTexts["En qué se va el dinero"].exists)
    }

    func testAddExpenseValidatesAndSaves() {
        let app = launch()
        app.tabBars.buttons["Movimientos"].tap()
        let add = app.buttons["movements.add"]
        XCTAssertTrue(add.waitForExistence(timeout: 5))
        add.tap()

        // Empty form: both fields fail, the summary lists them.
        app.buttons["editor.save"].tap()
        XCTAssertTrue(app.staticTexts["Revisá 2 campos"].waitForExistence(timeout: 2))

        // A mistyped decimal is rejected, never silently multiplied.
        let amount = app.textFields["editor.amount"]
        amount.tap()
        amount.typeText("1.5.2")
        let description = app.textFields["editor.description"]
        description.tap()
        description.typeText("Panadería")
        app.buttons["editor.save"].tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'Escribí un monto'")).firstMatch.waitForExistence(timeout: 2))

        amount.tap()
        amount.clearAndType("4.250")
        app.buttons["editor.save"].tap()

        // Durable outcome: the sheet closes and the new row is listed. (The "Gasto guardado"
        // status is intentionally transient, 4 s, so it is not a reliable assertion target.)
        XCTAssertTrue(app.buttons["editor.save"].waitForNonExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["Panadería"].waitForExistence(timeout: 10))
    }

    /// Saving only a new description must keep the stored cents and the stored category.
    func testEditKeepsTheStoredAmountAndCategory() {
        let app = launch()
        app.tabBars.buttons["Movimientos"].tap()
        let row = app.staticTexts["Feria del agricultor"]
        XCTAssertTrue(row.waitForExistence(timeout: 5))
        row.tap()
        let amount = app.textFields["editor.amount"]
        XCTAssertTrue(amount.waitForExistence(timeout: 5))
        XCTAssertEqual(amount.value as? String, "12.345,5", "the edit form shows the stored value, unrounded")
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "label == 'Feria' OR value == 'Feria'")).firstMatch.exists,
                      "the stored category stays selected")
        let description = app.textFields["editor.description"]
        description.tap()
        description.clearAndType("Feria de Zapote")
        app.buttons["editor.save"].tap()
        XCTAssertTrue(app.buttons["editor.save"].waitForNonExistence(timeout: 10))
        let edited = app.staticTexts["Feria de Zapote"]
        XCTAssertTrue(edited.waitForExistence(timeout: 10))
        edited.tap()
        XCTAssertTrue(amount.waitForExistence(timeout: 5))
        XCTAssertEqual(amount.value as? String, "12.345,5")
    }

    func testDeleteAsksAndRemovesTheRow() {
        let app = launch()
        app.tabBars.buttons["Movimientos"].tap()
        let row = app.staticTexts["Feria del agricultor"]
        XCTAssertTrue(row.waitForExistence(timeout: 5))
        row.press(forDuration: 1.0) // context menu: Editar / Eliminar
        let delete = app.buttons["Eliminar"].firstMatch
        XCTAssertTrue(delete.waitForExistence(timeout: 5))
        delete.tap()
        // The confirmation dialog repeats "Eliminar" as its destructive action.
        let confirm = app.buttons.matching(NSPredicate(format: "label == 'Eliminar'")).firstMatch
        XCTAssertTrue(confirm.waitForExistence(timeout: 5))
        confirm.tap()
        XCTAssertTrue(row.waitForNonExistence(timeout: 10))
    }

    func testEmptyAccountTeachesTheFirstAction() {
        // UX-6: nothing registered is unknown (never ₡0), and Qué sigue starts with the month's income.
        let app = launch("empty")
        XCTAssertTrue(app.staticTexts["Aún no puedo calcularlo"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.descendants(matching: .any)["home.next.action"].exists)
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Registrá tus ingresos del mes")).firstMatch.exists)
    }

    func testFailingBackendShowsRecovery() {
        let app = launch("failing", skipLogin: true)
        XCTAssertTrue(app.staticTexts["No pudimos cargar tu cuenta"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["Intentar de nuevo"].exists)
        XCTAssertTrue(app.buttons["Cerrar sesión"].exists)
    }

    func testNewUserGoesThroughProfileSetup() {
        let app = launch("newUser")
        let next = app.buttons["setup.continue"]
        XCTAssertTrue(next.waitForExistence(timeout: 5))
        next.tap() // name prefilled from the account
        app.buttons["Tomar control de mis finanzas"].tap()
        next.tap()
        next.tap()
        XCTAssertTrue(app.buttons["Entrar a DINCR"].waitForExistence(timeout: 2))
        app.buttons["Entrar a DINCR"].tap()
        // A11: a new account chooses its plan; paid plans wait for the stores.
        XCTAssertTrue(app.staticTexts["Elegí tu suscripción"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Próximamente en las tiendas"].exists)
        app.buttons["Elegir Free"].tap()
        XCTAssertTrue(app.staticTexts["Resultado del mes"].waitForExistence(timeout: 5))
    }

    func testLegalConsentIsRequiredBeforeTheApp() {
        let app = launch("legalRequired")
        let accept = app.buttons["legal.accept"]
        XCTAssertTrue(accept.waitForExistence(timeout: 5))
        XCTAssertFalse(accept.isEnabled)
        for id in ["legal.terms", "legal.privacy"] {
            app.switches[id].coordinate(withNormalizedOffset: CGVector(dx: 0.95, dy: 0.5)).tap()
        }
        XCTAssertTrue(accept.isEnabled)
        accept.tap()
        // Hoy loads its blocks after the consent is saved (10 s, like the other Hoy waits).
        XCTAssertTrue(app.staticTexts["Resultado del mes"].waitForExistence(timeout: 10))
    }

    private func open(_ identifier: String, in app: XCUIApplication) {
        let element = app.descendants(matching: .any)[identifier].firstMatch
        XCTAssertTrue(element.waitForExistence(timeout: 5), "missing \(identifier)")
        element.tap()
    }

    func testDebtPaymentIsRecorded() {
        let app = launch()
        // Hoy keeps its shortcut to the debts screen (managed in Plan → Deudas since UX-4).
        open("home.debts", in: app)
        let pay = app.buttons["debt.pay.31"]
        XCTAssertTrue(pay.waitForExistence(timeout: 5))
        pay.tap()
        let field = app.textFields["amount.field"]
        XCTAssertTrue(field.waitForExistence(timeout: 2))
        field.tap()
        field.typeText("1,5,0")
        app.buttons["amount.save"].tap()
        // Ambiguous input is refused on the device, never guessed.
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Escribí un monto")).firstMatch.waitForExistence(timeout: 2))
        field.clearAndType("10.000")
        app.buttons["amount.save"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["plan.notice"].waitForExistence(timeout: 5))
    }

    func testGoalContributionIsRecorded() {
        let app = launch()
        open("home.goals", in: app)
        let contribute = app.buttons["goal.contribute.41"]
        XCTAssertTrue(contribute.waitForExistence(timeout: 5))
        contribute.tap()
        let field = app.textFields["amount.field"]
        XCTAssertTrue(field.waitForExistence(timeout: 2))
        field.tap()
        field.typeText("25.000")
        app.buttons["amount.save"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["plan.notice"].waitForExistence(timeout: 5))
    }

    func testBasicHomeShowsItsDashboardAndBudget() {
        let app = launch(extra: ["-DincrPlan", "basic"])
        XCTAssertTrue(app.descendants(matching: .any)["home.status"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.descendants(matching: .any)["home.status.budget"].exists, "Basic adds the user's own budget left")
        // The budget lives in Perfil → Finanzas.
        app.tabBars.buttons["Perfil"].tap()
        open("profile.budget", in: app)
        XCTAssertTrue(app.buttons["budget.edit"].waitForExistence(timeout: 5))
    }

    func testFreePlanDoesNotOfferBasicTools() {
        let app = launch()
        XCTAssertTrue(app.descendants(matching: .any)["home.debts"].waitForExistence(timeout: 5))
        app.tabBars.buttons["Perfil"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["profile.subscription"].waitForExistence(timeout: 5))
        // PR 4: the rows stay visible, locked to the subscription that includes them.
        XCTAssertTrue(app.descendants(matching: .any)["profile.budget"].label.contains("Disponible desde Basic"))
        // §15 PR 10: Correos and Cuentas live in Patrimonio (locked there below VIP), no longer in Perfil.
        XCTAssertFalse(app.descendants(matching: .any)["profile.mail"].exists)
        XCTAssertFalse(app.descendants(matching: .any)["profile.accounts"].exists)
    }

    func testVipHomeShowsSafeToSpend() {
        let app = launch(extra: ["-DincrPlan", "vip"])
        XCTAssertTrue(app.descendants(matching: .any)["home.status.amount"].waitForExistence(timeout: 5))
        // UX-13: no DINCR tab; the monthly summary lives in Movimientos → Análisis, the strategy in Plan.
        XCTAssertFalse(app.tabBars.buttons["DINCR"].exists)
        app.tabBars.buttons["Movimientos"].tap()
        open("movements.analysis", in: app)
        XCTAssertTrue(app.descendants(matching: .any)["analysis.summary"].waitForExistence(timeout: 5))
        app.tabBars.buttons["Plan"].tap()
        open("plan.strategy", in: app)
        XCTAssertTrue(app.descendants(matching: .any)["strategy.dashboard"].waitForExistence(timeout: 10))
    }

    func testDollarExpenseAsksForTheUsersRate() {
        let app = launch()
        app.tabBars.buttons["Movimientos"].tap()
        let add = app.buttons["movements.add"]
        XCTAssertTrue(add.waitForExistence(timeout: 5))
        add.tap()
        let currency = app.segmentedControls["editor.currency"]
        XCTAssertTrue(currency.waitForExistence(timeout: 5))
        currency.buttons["USD"].tap()
        let rate = app.textFields["editor.rate"]
        XCTAssertTrue(rate.waitForExistence(timeout: 2))
        XCTAssertEqual(rate.value as? String, "507,5", "prefilled with the user's own latest rate, never a market rate")
        rate.tap()
        rate.clearAndType("")
        let amount = app.textFields["editor.amount"]
        amount.tap()
        amount.typeText("12")
        let description = app.textFields["editor.description"]
        description.tap()
        description.typeText("Libro")
        app.buttons["editor.save"].tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Escribí cuántos colones")).firstMatch.waitForExistence(timeout: 2))
        rate.tap()
        rate.typeText("510")
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Se guardará como")).firstMatch.waitForExistence(timeout: 2))
        app.buttons["editor.save"].tap()
        XCTAssertTrue(app.staticTexts["Libro"].waitForExistence(timeout: 10))
    }

    /// The flow of the Google OAuth verification video, on fixture data: Email Monitor → explanation
    /// (gmail.readonly) → consent → Connect Gmail → provider → back to DINCR → connected → sync →
    /// candidates → confirm. Only the provider page is simulated; the real one is DEVICE REQUIRED.
    func testEmailMonitorConnectReviewFlow() {
        let app = launch("mailOnboarding", extra: ["-DincrTab", "wealth"])
        open("wealth.connections", in: app)
        XCTAssertTrue(app.descendants(matching: .any)["mail.readonly"].waitForExistence(timeout: 5))
        let accept = app.buttons["mail.consent.accept"]
        XCTAssertTrue(accept.waitForExistence(timeout: 5))
        XCTAssertFalse(accept.isEnabled, "consent must be checked first")
        app.switches["mail.consent.toggle"].coordinate(withNormalizedOffset: CGVector(dx: 0.95, dy: 0.5)).tap()
        accept.tap()
        let connect = app.buttons["mail.connect"]
        XCTAssertTrue(connect.waitForExistence(timeout: 5))
        connect.tap()
        open("mail.scope.month", in: app)
        XCTAssertTrue(app.descendants(matching: .any)["mail.status.connected"].waitForExistence(timeout: 10))
        let sync = app.buttons["mail.sync"]
        XCTAssertTrue(sync.waitForExistence(timeout: 5))
        sync.tap()
        XCTAssertTrue(app.descendants(matching: .any)["mail.syncSummary"].waitForExistence(timeout: 10))
        let confirm = app.buttons["mail.accept.21"]
        XCTAssertTrue(confirm.waitForExistence(timeout: 10))
        confirm.tap()
        XCTAssertTrue(app.descendants(matching: .any)["mail.notice"].waitForExistence(timeout: 10))
        XCTAssertTrue(confirm.waitForNonExistence(timeout: 10), "a reviewed notice leaves the pending list")
        // A dollar notice cannot be confirmed as detected: it asks for the user's rate.
        XCTAssertFalse(app.buttons["mail.accept.22"].exists)
        XCTAssertTrue(app.buttons["mail.correct.22"].exists)
    }
}

extension XCUIElement {
    @MainActor
    func clearAndType(_ text: String) {
        guard let current = value as? String, !current.isEmpty else { typeText(text); return }
        typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: current.count))
        typeText(text)
    }
}
