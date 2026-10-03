import XCTest

/// The Plan tab (Aguinaldo, Estrategia, Salvavidas, Distribución), the relocated screens, Cuentas
/// sharing the Email Monitor's review, the onboarding logos, the financial situation's work days and
/// the Owner's financial analysis and receivables, on synthetic fixture data. Android: `PlanAccountsUiTest`.
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

    func testPlanHasExactlyTheFourRows() {
        let app = launch(plan: "vip", tab: "plan")
        for id in ["plan.aguinaldo", "plan.strategy", "plan.salvavidas", "plan.distribution"] {
            XCTAssertTrue(element(id, in: app).waitForExistence(timeout: 5), id)
        }
        for id in ["plan.debts", "plan.goals", "plan.budget", "plan.calendar", "plan.recurring", "plan.emergency"] {
            XCTAssertFalse(element(id, in: app).exists, "\(id) left the Plan tab")
        }
    }

    func testALockedRowOpensThePlans() {
        let app = launch(tab: "plan")
        XCTAssertTrue(text("Disponible desde Basic", in: app).waitForExistence(timeout: 5))
        XCTAssertTrue(text("Disponible desde VIP", in: app).exists)
        open("plan.strategy", in: app)
        XCTAssertTrue(text("Plan actual", in: app).waitForExistence(timeout: 10))
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

    // MARK: Strategy and distribution

    func testBasicStrategyFromRecordedIncomeSaysSo() {
        let app = launch(plan: "basic", tab: "plan")
        open("plan.strategy", in: app)
        XCTAssertTrue(text("Estimado con tus ingresos registrados (no declarado)", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Margen para decidir", in: app).exists)
    }

    func testBasicStrategyWithoutIncomeAsksForTheSituation() {
        let app = launch("empty", plan: "basic", tab: "plan")
        open("plan.strategy", in: app)
        XCTAssertTrue(element("strategy.needsIncome", in: app).waitForExistence(timeout: 10))
        open("strategy.completeSituation", in: app)
        XCTAssertTrue(element("situation.save", in: app).waitForExistence(timeout: 10))
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
        XCTAssertTrue(element("strategy.owner", in: app).exists)
    }

    // MARK: Salvavidas

    func testUnknownSavingsAreNeverZeroMonths() {
        let app = launch(plan: "vip", tab: "plan")
        open("plan.salvavidas", in: app)
        let coverage = element("salvavidas.coverage", in: app)
        XCTAssertTrue(coverage.waitForExistence(timeout: 10))
        XCTAssertEqual(coverage.label, "Sin dato")
        XCTAssertFalse(text("0 meses", in: app).exists)
        XCTAssertTrue(element("salvavidas.completeSituation", in: app).exists)
    }

    func testTheOwnerSalvavidasHasProtectedExpenses() {
        let app = launch(role: "owner", tab: "plan")
        open("plan.salvavidas", in: app)
        XCTAssertTrue(element("salvavidas.protect.62", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(element("salvavidas.editBalance", in: app).exists)
    }

    // MARK: Cuentas ↔ Correos (one review system)

    func testAcceptingInCuentasShowsInTheEmailMonitor() {
        let app = launch(plan: "vip", tab: "profile")
        open("profile.accounts", in: app)
        open("accounts.bank.bac", in: app)
        open("mail.accept.21", in: app)
        XCTAssertTrue(element("candidate.status.21", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Confirmado", in: app).exists)
        back(app); back(app)
        open("profile.mail", in: app)
        XCTAssertTrue(element("mail.correct.22", in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(element("mail.accept.21", in: app).exists, "reviewed in Cuentas: no longer pending in the Email Monitor")
    }

    func testRejectingInTheEmailMonitorShowsInCuentas() {
        let app = launch(plan: "vip", tab: "profile")
        open("profile.mail", in: app)
        open("mail.reject.21", in: app)
        XCTAssertTrue(element("mail.notice", in: app).waitForExistence(timeout: 10))
        back(app)
        open("profile.accounts", in: app)
        open("accounts.bank.bac", in: app)
        XCTAssertTrue(element("candidate.status.21", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Descartado", in: app).exists)
        XCTAssertFalse(element("mail.accept.21", in: app).exists)
    }

    func testAnUnknownBankIsGroupedUnderOtherInstitutions() {
        let app = launch(plan: "vip", tab: "profile")
        open("profile.accounts", in: app)
        XCTAssertTrue(element("accounts.bank.other", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Otras instituciones", in: app).exists)
        XCTAssertTrue(text("Banco Popular", in: app).exists)
        XCTAssertTrue(text("BAC", in: app).exists)
    }

    /// "Banco Popular" (the account's label) stores its notices as "popular" (the code): its
    /// movements are listed because Cuentas asks with the code.
    func testABankWhoseLabelDiffersFromItsCodeListsItsMovements() {
        let app = launch(plan: "vip", tab: "profile")
        open("profile.accounts", in: app)
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

    func testFixedIncomeSituationSendsTheWorkDays() {
        let app = launch(tab: "profile")
        open("profile.situation", in: app)
        let days = element("situation.workDays", in: app)
        XCTAssertTrue(days.waitForExistence(timeout: 10))
        XCTAssertEqual(days.value as? String, "5", "the web form's default, visible and editable")
        open("situation.save", in: app)
        // The fixture, like the backend, answers 422 without work_days_per_week.
        XCTAssertTrue(text("Guardado", in: app).waitForExistence(timeout: 10))
    }

    func testOnlyTheOwnerGetsTheFinancialAnalysis() {
        let owner = launch(role: "owner", tab: "profile")
        open("profile.jarvis", in: owner)
        open("jarvis.section.analysis", in: owner)
        XCTAssertTrue(element("jarvis.analysis.health", in: owner).waitForExistence(timeout: 10))
        XCTAssertTrue(element("jarvis.analysis.networth", in: owner).exists)
        owner.terminate()

        let user = launch(plan: "vip", tab: "profile")
        XCTAssertTrue(element("profile.situation", in: user).waitForExistence(timeout: 5))
        XCTAssertFalse(element("profile.jarvis", in: user).exists)
        XCTAssertFalse(element("jarvis.section.analysis", in: user).exists)
    }

    /// Cuentas por cobrar (JARVIS · Control de dinero): the Owner reads them; no plan reaches JARVIS.
    func testOnlyTheOwnerGetsTheReceivables() {
        let owner = launch(role: "owner", tab: "profile")
        open("profile.jarvis", in: owner)
        open("jarvis.section.money_control", in: owner)
        XCTAssertTrue(element("jarvis.receivables.summary", in: owner).waitForExistence(timeout: 10))
        XCTAssertTrue(element("jarvis.receivables.item.1", in: owner).exists)
        XCTAssertFalse(element("jarvis.restoring", in: owner).exists, "money control is no longer a placeholder")
        owner.terminate()

        for plan in ["free", "basic", "vip"] {
            let user = launch(plan: plan == "free" ? nil : plan, tab: "profile")
            XCTAssertTrue(element("profile.situation", in: user).waitForExistence(timeout: 5))
            XCTAssertFalse(element("profile.jarvis", in: user).exists)
            XCTAssertFalse(element("jarvis.section.money_control", in: user).exists)
            user.terminate()
        }
    }
}
