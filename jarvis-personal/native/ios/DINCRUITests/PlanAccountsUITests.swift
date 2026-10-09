import XCTest

/// The Plan tab (Aguinaldo, Estrategia, Salvavidas, Distribución), the relocated screens, Cuentas
/// sharing the Email Monitor's review, the onboarding logos, the financial situation's work days and
/// the Owner's financial analysis, on synthetic fixture data. Android: `PlanAccountsUiTest`.
@MainActor
final class PlanAccountsUITests: XCTestCase {
    private func launch(_ scenario: String = "populated", plan: String? = nil, role: String? = nil, tab: String? = nil) -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", scenario, "-DincrSkipLogin", "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        if let plan { arguments += ["-DincrPlan", plan] }
        if let role { arguments += ["-DincrRole", role] }
        if let tab { arguments += ["-DincrTab", tab] }
        app.launchArguments = arguments
        app.launch()
        return app
    }

    private func element(_ identifier: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any)[identifier].firstMatch
    }

    private func open(_ identifier: String, in app: XCUIApplication) {
        let target = element(identifier, in: app)
        XCTAssertTrue(target.waitForExistence(timeout: 10), "missing \(identifier)")
        if !target.isHittable { app.swipeUp() }
        target.tap()
    }

    /// Any element whose label contains the text (rows combine their texts into one element).
    private func text(_ content: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", content)).firstMatch
    }

    private func back(_ app: XCUIApplication) {
        app.navigationBars.buttons.element(boundBy: 0).tap()
    }

    // MARK: Plan tab

    func testPlanHasExactlyItsRows() {
        let app = launch(plan: "vip", tab: "plan")
        for id in ["plan.aguinaldo", "plan.strategy", "plan.debts", "plan.salvavidas", "plan.distribution"] {
            XCTAssertTrue(element(id, in: app).waitForExistence(timeout: 5), id)
        }
        for id in ["plan.goals", "plan.budget", "plan.calendar", "plan.recurring", "plan.emergency"] {
            XCTAssertFalse(element(id, in: app).exists, "\(id) left the Plan tab")
        }
    }

    func testALockedRowOpensThePlans() {
        let app = launch(tab: "plan")
        XCTAssertTrue(text("Disponible desde Basic", in: app).waitForExistence(timeout: 5))
        XCTAssertTrue(text("Disponible desde VIP", in: app).exists)
        open("plan.strategy", in: app)
        XCTAssertTrue(text("Suscripción actual", in: app).waitForExistence(timeout: 10))
    }

    /// UX-4 — Plan → Deudas is where debts are managed, for every plan, with the actions each plan
    /// has today: Free records, pays and deletes; editing stays Basic+ (backend gate). Hoy keeps its
    /// shortcut to the same screen.
    func testDebtsAreManagedFromPlanForEveryPlan() {
        let free = launch(tab: "plan")
        open("plan.debts", in: free)
        XCTAssertTrue(free.navigationBars["Deudas"].waitForExistence(timeout: 10))
        XCTAssertTrue(element("debts.add", in: free).exists, "Free records its debts")
        XCTAssertTrue(free.buttons["debt.pay.31"].waitForExistence(timeout: 10), "Free records a payment")
        free.buttons["Más acciones"].firstMatch.tap()
        XCTAssertTrue(free.buttons["Eliminar"].waitForExistence(timeout: 5), "Free deletes")
        XCTAssertFalse(free.buttons["Editar"].exists, "editing stays Basic+ (PUT is gated strategy_basic)")
        free.terminate()

        let basic = launch(plan: "basic", tab: "plan")
        open("plan.debts", in: basic)
        XCTAssertTrue(basic.buttons["debt.pay.31"].waitForExistence(timeout: 10))
        basic.buttons["Más acciones"].firstMatch.tap()
        XCTAssertTrue(basic.buttons["Editar"].waitForExistence(timeout: 5), "Basic edits")
        basic.buttons["Editar"].tap()
        XCTAssertTrue(element("debt.save", in: basic).waitForExistence(timeout: 5), "the edit form")
        basic.terminate()

        for (plan, role) in [("vip", "user"), (nil, "owner")] as [(String?, String)] {
            let app = launch(plan: plan, role: role, tab: "plan")
            open("plan.debts", in: app)
            XCTAssertTrue(app.navigationBars["Deudas"].waitForExistence(timeout: 10), "\(plan ?? role) reaches Deudas")
            app.terminate()
        }
    }

    func testANewDebtIsRecordedFromPlan() {
        let app = launch(tab: "plan")
        open("plan.debts", in: app)
        open("debts.add", in: app)
        let name = element("debt.name", in: app)
        XCTAssertTrue(name.waitForExistence(timeout: 5))
        name.tap(); name.typeText("Préstamo de prueba")
        let remaining = element("debt.remaining", in: app)
        remaining.tap(); remaining.typeText("120.000")
        open("debt.save", in: app)
        XCTAssertTrue(element("plan.notice", in: app).waitForExistence(timeout: 10), "the debt is saved")
        XCTAssertTrue(text("Préstamo de prueba", in: app).waitForExistence(timeout: 10), "and listed")
    }

    func testRelocatedScreensAreReachable() {
        let app = launch(plan: "basic")
        XCTAssertTrue(element("home.debts", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(element("home.goals", in: app).exists)
        app.tabBars.buttons["Perfil"].tap()
        for id in ["profile.budget", "profile.calendar", "profile.recurring"] {
            XCTAssertTrue(element(id, in: app).waitForExistence(timeout: 5), id)
        }
        open("profile.calendar", in: app)
        XCTAssertTrue(app.navigationBars["Calendario"].waitForExistence(timeout: 10))
    }

    // MARK: Subscription (UX-12: Free / Basic / VIP; "Plan" is the financial plan)

    func testProfileShowsTheSubscriptionOfEachTier() {
        for (plan, name) in [(nil, "Gratis"), ("basic", "Basic"), ("vip", "VIP")] as [(String?, String)] {
            let app = launch(plan: plan, tab: "profile")
            open("profile.subscription", in: app)
            XCTAssertTrue(app.navigationBars["Suscripción"].waitForExistence(timeout: 10), plan ?? "free")
            XCTAssertTrue(text("Suscripción actual", in: app).exists, plan ?? "free")
            XCTAssertTrue(text(name, in: app).exists, plan ?? "free")
            XCTAssertFalse(element("subscription.owner", in: app).exists)
            app.terminate()
        }
    }

    func testTheOwnerIsNotAPurchasableSubscription() {
        let app = launch(role: "owner", tab: "profile")
        open("profile.subscription", in: app)
        XCTAssertTrue(element("subscription.owner", in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(text("Suscripción actual", in: app).exists, "no tier is shown for the Owner")
        XCTAssertFalse(app.buttons.matching(NSPredicate(format: "label CONTAINS 'Elegir' OR label CONTAINS 'Cambiar'")).firstMatch.exists, "nothing to choose")
    }

    func testTuPlanDelMesStaysTheFinancialPlan() {
        let app = launch(plan: "basic", tab: "plan")
        XCTAssertTrue(app.navigationBars["Plan"].waitForExistence(timeout: 10))
        open("plan.strategy", in: app)
        XCTAssertTrue(text("Tu plan del mes", in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(text("Suscripción actual", in: app).exists, "the financial plan is not the subscription")
    }

    // MARK: Recurring commitments (UX-9: every plan)

    func testFreeCreatesEditsAndDeletesRecurringCommitments() {
        let app = launch(tab: "profile")
        XCTAssertTrue(element("profile.recurring", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(element("profile.budget", in: app).label.contains("Disponible desde Basic"), "budget stays Basic (locked)")
        XCTAssertTrue(element("profile.calendar", in: app).label.contains("Disponible desde Basic"), "calendar stays Basic (locked)")
        open("profile.recurring", in: app)

        // Create.
        let add = app.navigationBars.buttons["Agregar"]
        XCTAssertTrue(add.waitForExistence(timeout: 10))
        add.tap()
        let name = app.textFields["recurring.name"]
        XCTAssertTrue(name.waitForExistence(timeout: 5))
        name.tap(); name.typeText("Gimnasio sintético")
        let amount = app.textFields["recurring.amount"]
        amount.tap(); amount.typeText("15000")
        app.navigationBars.buttons["Guardar"].tap()
        XCTAssertTrue(text("Recurrente agregado", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Gimnasio sintético", in: app).exists)

        // Edit (every field, through the same form).
        open("recurring.edit", in: app)
        let editName = app.textFields["recurring.name"]
        XCTAssertTrue(editName.waitForExistence(timeout: 5))
        editName.tap()
        editName.press(forDuration: 1.0)
        if app.menuItems["Select All"].waitForExistence(timeout: 2) { app.menuItems["Select All"].tap() }
        editName.typeText("Editado sintético")
        app.navigationBars.buttons["Guardar"].tap()
        XCTAssertTrue(text("Recurrente actualizado", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Editado sintético", in: app).exists)

        // Delete.
        open("recurring.delete", in: app)
        // The dialog repeats "Eliminar"; the rows' own buttons carry the `recurring.delete` identifier.
        let confirm = app.buttons.matching(NSPredicate(format: "label == 'Eliminar' AND identifier != 'recurring.delete'")).firstMatch
        XCTAssertTrue(confirm.waitForExistence(timeout: 5))
        confirm.tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Editado sintético")).firstMatch.waitForNonExistence(timeout: 10))
    }

    // MARK: Strategy and distribution

    func testBasicStrategyFromRecordedIncomeSaysSo() {
        let app = launch(plan: "basic", tab: "plan")
        open("plan.strategy", in: app)
        XCTAssertTrue(text("Estimado con tus ingresos registrados (no declarado)", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Libre después de tus compromisos", in: app).exists)
    }

    func testBasicStrategyWithoutIncomeAsksForIngresosYBase() {
        let app = launch("empty", plan: "basic", tab: "plan")
        open("plan.strategy", in: app)
        XCTAssertTrue(element("strategy.needsIncome", in: app).waitForExistence(timeout: 10))
        open("strategy.completeIncomeBase", in: app)
        XCTAssertTrue(element("incomeBase.save", in: app).waitForExistence(timeout: 10))
    }

    func testDistributionReadsTheStrategyDashboard() {
        let app = launch(plan: "vip", tab: "plan")
        open("plan.distribution", in: app)
        XCTAssertTrue(element("distribution.dashboard", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Ataque de deuda · Tarjeta de crédito", in: app).exists)
        XCTAssertTrue(text("Sobrante para repartir", in: app).exists)
        XCTAssertFalse(text("Efectivo disponible ahora", in: app).exists, "Users never see a cash balance")
    }

    func testTheOwnerStrategyShowsHisCycle() {
        let app = launch(role: "owner", tab: "plan")
        open("plan.strategy", in: app)
        XCTAssertTrue(element("strategy.dashboard", in: app).waitForExistence(timeout: 10))
        // UX-3: the Owner's cycle is in "Tu plan del mes" → "Ver todo el detalle".
        open("plan.month.detail", in: app)
        XCTAssertTrue(element("strategy.owner", in: app).waitForExistence(timeout: 10))
    }

    /// UX-3 — "Tu plan del mes": the result first (amount to plan, split, one-sentence why), every
    /// historical detail one tap away, and Distribución de dinero still reachable on its own row.
    func testTheMonthPlanLeadsWithTheResultAndKeepsEveryDetail() {
        let app = launch(plan: "vip", tab: "plan")
        XCTAssertTrue(text("Tu plan del mes", in: app).waitForExistence(timeout: 5))
        open("plan.strategy", in: app)
        XCTAssertTrue(app.navigationBars["Tu plan del mes"].waitForExistence(timeout: 10))
        XCTAssertTrue(text("Sobrante para repartir", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Atacar deuda: Tarjeta de crédito", in: app).exists, "the priority, in one sentence")
        XCTAssertTrue(element("plan.month.split", in: app).exists)
        XCTAssertTrue(text("Ataque de deuda · Tarjeta de crédito", in: app).exists, "each part with its label")
        XCTAssertFalse(element("plan.month.salvavidas", in: app).exists, "the detail starts closed")
        open("plan.month.why", in: app)
        XCTAssertTrue(text("De dónde sale", in: app).waitForExistence(timeout: 5))
        open("plan.month.detail", in: app)
        XCTAssertTrue(element("plan.month.salvavidas", in: app).waitForExistence(timeout: 5))
        XCTAssertFalse(element("strategy.owner", in: app).exists, "Users never see the Owner's cycle")
        XCTAssertFalse(text("Efectivo disponible ahora", in: app).exists, "Users never see a cash balance")
        back(app)
        open("plan.distribution", in: app)
        XCTAssertTrue(element("distribution.dashboard", in: app).waitForExistence(timeout: 10))
    }

    // MARK: Salvavidas

    func testUnknownSavingsAreNeverZeroMonths() {
        let app = launch(plan: "vip", tab: "plan")
        open("plan.salvavidas", in: app)
        let coverage = element("salvavidas.coverage", in: app)
        XCTAssertTrue(coverage.waitForExistence(timeout: 10))
        XCTAssertEqual(coverage.label, "Sin dato")
        XCTAssertFalse(text("0 meses", in: app).exists)
        XCTAssertTrue(element("salvavidas.completeSavings", in: app).exists)
    }

    func testTheOwnerSalvavidasHasProtectedExpenses() {
        let app = launch(role: "owner", tab: "plan")
        open("plan.salvavidas", in: app)
        XCTAssertTrue(element("salvavidas.protect.62", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(element("salvavidas.editBalance", in: app).exists)
    }

    // MARK: Cuentas ↔ Correos (one review system; §15 PR 10: both in Patrimonio)

    func testAcceptingInCuentasShowsInTheEmailMonitor() {
        let app = launch(plan: "vip", tab: "wealth")
        open("wealth.accounts", in: app)
        open("accounts.bank.bac", in: app)
        open("mail.accept.21", in: app)
        XCTAssertTrue(element("candidate.status.21", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Confirmado", in: app).exists)
        back(app); back(app)
        open("wealth.connections", in: app)
        XCTAssertTrue(element("mail.correct.22", in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(element("mail.accept.21", in: app).exists, "reviewed in Cuentas: no longer pending in the Email Monitor")
    }

    func testRejectingInTheEmailMonitorShowsInCuentas() {
        let app = launch(plan: "vip", tab: "wealth")
        open("wealth.connections", in: app)
        open("mail.reject.21", in: app)
        XCTAssertTrue(element("mail.notice", in: app).waitForExistence(timeout: 10))
        back(app)
        open("wealth.accounts", in: app)
        open("accounts.bank.bac", in: app)
        XCTAssertTrue(element("candidate.status.21", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Descartado", in: app).exists)
        XCTAssertFalse(element("mail.accept.21", in: app).exists)
    }

    func testAnUnknownBankIsGroupedUnderOtherInstitutions() {
        let app = launch(plan: "vip", tab: "wealth")
        open("wealth.accounts", in: app)
        XCTAssertTrue(element("accounts.bank.other", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Otras instituciones", in: app).exists)
        XCTAssertTrue(text("Banco Popular", in: app).exists)
        XCTAssertTrue(text("BAC", in: app).exists)
    }

    /// "Banco Popular" (the account's label) stores its notices as "popular" (the code): its
    /// movements are listed because Cuentas asks with the code.
    func testABankWhoseLabelDiffersFromItsCodeListsItsMovements() {
        let app = launch(plan: "vip", tab: "wealth")
        open("wealth.accounts", in: app)
        open("accounts.bank.popular", in: app)
        XCTAssertTrue(element("mail.reject.23", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Museo", in: app).exists)
    }

    // MARK: Onboarding, situation, Owner analysis

    func testOnboardingShowsTheBankLogosAsAPreference() {
        let app = launch("newUser")
        let next = app.buttons["setup.continue"]
        XCTAssertTrue(next.waitForExistence(timeout: 5))
        next.tap()
        app.buttons["Tomar control de mis finanzas"].tap()
        next.tap()
        next.tap()
        XCTAssertTrue(element("setup.bank.bac", in: app).waitForExistence(timeout: 5))
        XCTAssertTrue(element("setup.bank.scotiabank", in: app).exists)
        XCTAssertTrue(text("no conecta tus cuentas", in: app).exists)
    }

    func testFixedIncomeSendsTheWorkDaysFromIngresosYBase() {
        // UX-7: the declared income lives in Plan → Ingresos y base (no Situación screen in Perfil).
        let app = launch(tab: "plan")
        open("plan.incomeBase", in: app)
        let days = element("incomeBase.workDays", in: app)
        XCTAssertTrue(days.waitForExistence(timeout: 10))
        XCTAssertEqual(days.value as? String, "5", "the web form's default, visible and editable")
        open("incomeBase.save", in: app)
        // The fixture, like the backend, answers 422 without work_days_per_week.
        XCTAssertTrue(text("Guardado", in: app).waitForExistence(timeout: 10))
    }

    func testFreeKeepsEveryDeclaredFigureInItsHomeAndPerfilHasNoSituacion() {
        // UX-7: income and essential expenses in Plan → Ingresos y base; savings in Metas y ahorro.
        let app = launch(tab: "plan")
        open("plan.incomeBase", in: app)
        XCTAssertTrue(text("Gastos esenciales del mes", in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(text("Ahorros disponibles", in: app).exists, "savings live in Ahorros")
        app.tabBars.buttons["Hoy"].tap()
        open("home.goals", in: app)
        open("goals.declaredSavings", in: app)
        XCTAssertTrue(text("Ahorros disponibles", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Meta de fondo de emergencia", in: app).exists)
        app.tabBars.buttons["Perfil"].tap()
        XCTAssertTrue(element("profile.subscription", in: app).waitForExistence(timeout: 5))
        XCTAssertFalse(element("profile.situation", in: app).exists)
    }

    func testVipSeesDincrsRecommendationAndSetsOnlyTheMinimum() {
        // Saved with the declared profile: without an income, the settings say where to declare it.
        let undeclared = launch(plan: "vip", tab: "plan")
        open("plan.strategy", in: undeclared)
        open("plan.month.preferences", in: undeclared)
        XCTAssertTrue(element("planPreferences.declareIncome", in: undeclared).waitForExistence(timeout: 10))
        XCTAssertFalse(element("planPreferences.save", in: undeclared).exists)
        undeclared.terminate()

        // UX-8: DINCR's recommendation is shown, and the priority is not a free choice in the settings.
        let app = launch("store", plan: "vip", tab: "plan")  // a declared fixed income
        open("plan.strategy", in: app)
        XCTAssertTrue(element("plan.month.recommendedPriority", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Recomendación de DINCR", in: app).exists)
        open("plan.month.preferences", in: app)
        XCTAssertTrue(element("planPreferences.minimum", in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(text("Prioridad", in: app).exists, "no priority picker")
        open("planPreferences.save", in: app)
        XCTAssertTrue(text("Guardado", in: app).waitForExistence(timeout: 10))
        app.terminate()

        // Basic: DINCR's recommendation, no settings to change it.
        let basic = launch(plan: "basic", tab: "plan")
        open("plan.strategy", in: basic)
        XCTAssertTrue(element("plan.month.recommendedPriority", in: basic).waitForExistence(timeout: 10))
        XCTAssertFalse(element("plan.month.preferences", in: basic).exists, "the settings are VIP")
        basic.terminate()

        // Free: no strategy, so no priority and no recommendation.
        let free = launch(tab: "plan")
        XCTAssertTrue(element("plan.strategy", in: free).waitForExistence(timeout: 10))
        XCTAssertFalse(element("plan.month.recommendedPriority", in: free).exists)
    }

    func testOnlyTheOwnerGetsTheFinancialAnalysis() {
        let owner = launch(role: "owner", tab: "profile")
        open("profile.jarvis", in: owner)
        open("jarvis.section.analysis", in: owner)
        XCTAssertTrue(element("jarvis.analysis.health", in: owner).waitForExistence(timeout: 10))
        XCTAssertTrue(element("jarvis.analysis.networth", in: owner).exists)
        owner.terminate()

        let user = launch(plan: "vip", tab: "profile")
        XCTAssertTrue(element("profile.subscription", in: user).waitForExistence(timeout: 5))
        XCTAssertFalse(element("profile.jarvis", in: user).exists)
        XCTAssertFalse(element("jarvis.section.analysis", in: user).exists)
    }
}
