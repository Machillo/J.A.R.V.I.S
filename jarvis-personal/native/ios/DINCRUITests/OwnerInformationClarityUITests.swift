import XCTest

/// Owner information clarity on the fixtures (OwnerReadingViews.swift): Movimientos → Resumen del mes
/// reads the Owner's ledger (this month not complete yet; a closed month with a loan apart from income
/// and gross payroll apart), Plan → Tu plan del mes shows "Este ciclo" and "Tu ciclo" with their dates,
/// and JARVIS → Análisis lists the months not complete yet. VIP keeps the plain summary and "Tu mes".
/// Spanish and English; each screen is attached as a screenshot. Fixture data only.
final class OwnerInformationClarityUITests: XCTestCase {
    private func launch(_ language: String, plan: String = "vip", role: String? = "owner", tab: String) -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrPlan", plan, "-DincrTab", tab,
                               "-AppleLanguages", "(\(language))", "-AppleLocale", language == "es" ? "es_CR" : "en_US"]
            + (role.map { ["-DincrRole", $0] } ?? [])
        app.launch()
        return app
    }

    private func element(_ id: String, in app: XCUIApplication) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }

    private func text(_ content: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", content)).firstMatch
    }

    private func open(_ id: String, in app: XCUIApplication) {
        let target = element(id, in: app)
        XCTAssertTrue(target.waitForExistence(timeout: 10), "missing \(id)")
        if !target.isHittable { app.swipeUp() }
        target.tap()
    }

    /// Scrolls down until the text is on screen (the screens are long), at most a few times.
    private func reveal(_ content: String, in app: XCUIApplication, _ context: String) {
        let target = text(content, in: app)
        XCTAssertTrue(target.waitForExistence(timeout: 10) || { for _ in 0..<8 where !target.exists { app.swipeUp() }; return target.exists }(),
                      "\(context): missing “\(content)”")
        for _ in 0..<8 where !target.isHittable { app.swipeUp() }
    }

    /// Opens a disclosure of the strategy screen ("¿Por qué?", "Ver todo el detalle"), scrolling to it first.
    private func expand(_ id: String, in app: XCUIApplication) {
        let target = element(id, in: app)
        XCTAssertTrue(target.waitForExistence(timeout: 10), "missing \(id)")
        for _ in 0..<8 where !target.isHittable { app.swipeUp() }
        target.tap()
    }

    private func snapshot(_ name: String, _ app: XCUIApplication) {
        let shot = XCTAttachment(screenshot: app.screenshot())
        shot.name = name
        shot.lifetime = .keepAlways
        add(shot)
    }

    private func pick(_ language: String, _ es: String, _ en: String) -> String { language == "es" ? es : en }

    func testTheOwnersMonthSummaryReadsTheLedger() {
        for l in ["es", "en"] {
            let app = launch(l, tab: "movements")
            open("movements.analysis", in: app)
            open("analysis.summary", in: app)
            // This month: a mail notice still to review.
            XCTAssertTrue(element("summary.owner.month", in: app).waitForExistence(timeout: 10), l)
            XCTAssertTrue(text(pick(l, "Este mes todavía no está completo", "This month isn’t complete yet"), in: app).exists, l)
            XCTAssertTrue(text(pick(l, "avisos de correo de este mes sin revisar", "mail notices from this month not reviewed"), in: app).exists, l)
            XCTAssertTrue(text(pick(l, "Resultado del mes", "Result of the month"), in: app).exists, l)
            snapshot("\(l)-summary-current", app)

            // The month before: complete, a loan apart from income and the gross payroll apart.
            app.buttons[pick(l, "Mes anterior", "Previous month")].firstMatch.tap()
            XCTAssertTrue(text(pick(l, "Mes completo", "Complete month"), in: app).waitForExistence(timeout: 10), l)
            reveal(pick(l, "Otro dinero que entró (no es ingreso)", "Other money in (not income)"), in: app, l)
            XCTAssertTrue(text(pick(l, "Préstamos recibidos", "Loans received"), in: app).exists, l)
            snapshot("\(l)-summary-previous-inflows", app)
            reveal(pick(l, "Nómina bruta registrada (aparte)", "Gross payroll recorded (apart)"), in: app, l)
            XCTAssertTrue(text(pick(l, "Horas extra (bruto)", "Overtime (gross)"), in: app).exists, l)
            XCTAssertTrue(text(pick(l, "Bonos (bruto)", "Bonuses (gross)"), in: app).exists, l)
            XCTAssertFalse(text(pick(l, "Rebajos por vacaciones", "Leave deductions"), in: app).exists, "\(l): a zero part is not listed")
            app.swipeUp()  // the section starts under the tab bar
            snapshot("\(l)-summary-previous-payroll", app)
            app.terminate()
        }
    }

    func testTheOwnersPlanShowsThisCycleAndYourCycleWithTheirDates() {
        for l in ["es", "en"] {
            let app = launch(l, tab: "plan")
            open("plan.strategy", in: app)
            XCTAssertTrue(element("strategy.dashboard", in: app).waitForExistence(timeout: 10), l)
            // "¿Por qué?": the formula's income line is the income still to come in the cycle.
            expand("plan.month.why", in: app)
            reveal(pick(l, "Ingresos por recibir en el ciclo", "Income still to come this cycle"), in: app, l)
            snapshot("\(l)-plan-why", app)
            expand("plan.month.detail", in: app)
            reveal(pick(l, "Este ciclo", "This cycle"), in: app, l)
            XCTAssertTrue(text(pick(l, "Ciclo: ", "Cycle: "), in: app).exists, "\(l): the cycle's dates")
            XCTAssertTrue(text(pick(l, "Para uso libre en este ciclo", "Free to use this cycle"), in: app).exists, l)
            XCTAssertFalse(text(pick(l, "Tu mes", "Your month"), in: app).exists, "\(l): the Owner reads a cycle, not a month")
            snapshot("\(l)-plan-this-cycle", app)
            reveal(pick(l, "Tu ciclo", "Your cycle"), in: app, l)
            reveal(pick(l, "Estado de cuenta: ", "Statement: "), in: app, l)
            XCTAssertTrue(text(pick(l, "Gastos después del corte", "Spending after the statement cut"), in: app).exists, l)
            snapshot("\(l)-plan-your-cycle", app)
            app.terminate()
        }
    }

    func testTheOwnersAnalysisListsTheMonthsNotCompleteYet() {
        for l in ["es", "en"] {
            let app = launch(l, tab: "profile")
            open("profile.jarvis", in: app)
            open("jarvis.section.analysis", in: app)
            reveal(pick(l, "Meses todavía incompletos", "Months not complete yet"), in: app, l)
            XCTAssertTrue(element("jarvis.analysis.incomplete", in: app).exists, l)
            snapshot("\(l)-jarvis-analysis", app)
            app.terminate()
        }
    }

    func testVipKeepsThePlainSummaryAndYourMonth() {
        let app = launch("es", role: nil, tab: "movements")
        open("movements.analysis", in: app)
        open("analysis.summary", in: app)
        XCTAssertTrue(text("Balance", in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(element("summary.owner.month", in: app).exists, "VIP never reads the Owner's ledger")
        XCTAssertFalse(text("Este mes todavía no está completo", in: app).exists)
        app.terminate()

        let plan = launch("es", role: nil, tab: "plan")
        open("plan.strategy", in: plan)
        XCTAssertTrue(element("strategy.dashboard", in: plan).waitForExistence(timeout: 10))
        expand("plan.month.detail", in: plan)
        reveal("Tu mes", in: plan, "vip")
        XCTAssertTrue(text("Podés gastar con tranquilidad", in: plan).exists)
        XCTAssertFalse(text("Este ciclo", in: plan).exists)
        XCTAssertFalse(text("Tu ciclo", in: plan).exists)
    }
}
