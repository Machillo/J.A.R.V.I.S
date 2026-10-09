import XCTest

/// B17 — pull to refresh on Plan, Patrimonio and Perfil, as Hoy and Movimientos already had: every
/// plan keeps its rows and its locks, a refresh that fails keeps the screen and says so in the
/// app-wide notice (read by VoiceOver), and the navigation stays where it was. Android twin:
/// `PullToRefreshUiTest`. Fixture data only; `-DincrRefreshFails` makes the identity read again fail
/// like an unreachable server.
final class PullToRefreshUITests: XCTestCase {
    private let failureNotice = "No pudimos actualizar. Seguís viendo la información anterior."

    private func launch(plan: String? = nil, role: String? = nil, tab: String, refreshFails: Bool = false) -> XCUIApplication {
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrTab", tab,
                         "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        if let plan { arguments += ["-DincrPlan", plan] }
        if let role { arguments += ["-DincrRole", role] }
        if refreshFails { arguments.append("-DincrRefreshFails") }
        app.launchArguments = arguments
        app.launch()
        return app
    }

    private func element(_ id: String, in app: XCUIApplication) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }

    private func text(_ content: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", content)).firstMatch
    }

    /// The gesture itself: a drag down from the top of the content.
    private func pull(_ app: XCUIApplication) {
        let window = app.windows.firstMatch
        window.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.3))
            .press(forDuration: 0.05, thenDragTo: window.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.9)))
    }

    private func label(_ id: String, in app: XCUIApplication) -> String {
        let target = element(id, in: app)
        XCTAssertTrue(target.waitForExistence(timeout: 10), "missing \(id)")
        return target.label
    }

    /// Pulls and checks that the same rows, with the same locks, are still there and nothing failed.
    private func pullKeeping(_ ids: [String], in app: XCUIApplication, _ context: String) {
        let before = ids.map { label($0, in: app) }
        pull(app)
        // The refresh is done when the identity was read again; wait past it.
        sleep(1)
        XCTAssertEqual(ids.map { label($0, in: app) }, before, "\(context): rows or locks changed")
        XCTAssertFalse(element("app.notice", in: app).exists, "\(context): a successful refresh says nothing")
    }

    func testEveryPlanPullsPlanPatrimonioAndPerfilAndKeepsItsRowsAndLocks() {
        for (plan, role) in [(nil, nil), ("basic", nil), ("vip", nil), ("vip", "owner")] as [(String?, String?)] {
            let context = role ?? plan ?? "free"
            let app = launch(plan: plan, role: role, tab: "plan")
            let strategy = label("plan.strategy", in: app)
            XCTAssertEqual(strategy.contains("Disponible desde Basic"), plan == nil, "\(context): Tu plan del mes")
            pullKeeping(["plan.aguinaldo", "plan.strategy", "plan.debts", "plan.incomeBase", "plan.salvavidas", "plan.distribution"], in: app, "\(context) Plan")
            XCTAssertTrue(app.tabBars.buttons["Plan"].isSelected, "\(context): still on Plan")

            app.tabBars.buttons["Patrimonio"].tap()
            XCTAssertTrue(element("wealth.debts.composition", in: app).waitForExistence(timeout: 10), "\(context): debts")
            XCTAssertEqual(label("wealth.accounts", in: app).contains("Disponible desde VIP"), plan != "vip", "\(context): Cuentas")
            pullKeeping(["wealth.accounts", "wealth.connections", "wealth.debts"], in: app, "\(context) Patrimonio")
            XCTAssertTrue(element("wealth.debts.composition", in: app).exists, "\(context): the debts after the refresh")

            app.tabBars.buttons["Perfil"].tap()
            pullKeeping(["profile.subscription", "profile.security"], in: app, "\(context) Perfil")
            XCTAssertEqual(element("profile.jarvis", in: app).exists, role == "owner", "\(context): JARVIS only for the Owner")
            app.terminate()
        }
    }

    func testAFailedRefreshKeepsTheScreenAndSaysSoInTheNotice() {
        let app = launch(plan: "vip", tab: "wealth", refreshFails: true)
        XCTAssertTrue(element("wealth.debts.composition", in: app).waitForExistence(timeout: 10))
        let accounts = label("wealth.accounts", in: app)
        pull(app)
        let notice = element("app.notice", in: app)
        XCTAssertTrue(notice.waitForExistence(timeout: 10), "the failure is said")
        XCTAssertEqual(notice.label, failureNotice, "VoiceOver reads the notice")
        XCTAssertTrue(element("wealth.debts.composition", in: app).exists, "the debts stay")
        XCTAssertEqual(label("wealth.accounts", in: app), accounts, "the plan's rows stay")
        XCTAssertTrue(app.tabBars.buttons["Patrimonio"].isSelected, "no error screen replaces the app")

        for (tab, id) in [("Plan", "plan.strategy"), ("Perfil", "profile.subscription")] {
            XCTAssertTrue(notice.waitForNonExistence(timeout: 10), "the previous notice left")
            app.tabBars.buttons[tab].tap()
            let before = label(id, in: app)
            pull(app)
            XCTAssertTrue(element("app.notice", in: app).waitForExistence(timeout: 10), "\(tab): the failure is said")
            XCTAssertEqual(label(id, in: app), before, "\(tab): the screen stays")
        }
    }

    func testARefreshKeepsTheNavigationOfEveryTab() {
        let app = launch(tab: "profile")
        element("profile.subscription", in: app).tap()
        XCTAssertTrue(text("Suscripción actual", in: app).waitForExistence(timeout: 10))
        app.tabBars.buttons["Plan"].tap()
        XCTAssertTrue(element("plan.aguinaldo", in: app).waitForExistence(timeout: 10))
        pull(app)
        sleep(1)
        app.tabBars.buttons["Perfil"].tap()
        XCTAssertTrue(text("Suscripción actual", in: app).waitForExistence(timeout: 10), "Perfil is still on Suscripción")
        XCTAssertTrue(app.navigationBars.buttons["Perfil"].exists, "with its way back")
    }

    func testHoyAndMovimientosStillRefresh() {
        let app = launch(tab: "home")
        XCTAssertTrue(element("home.today", in: app).waitForExistence(timeout: 10))
        pull(app)
        sleep(1)
        XCTAssertTrue(element("home.today", in: app).waitForExistence(timeout: 10), "Hoy after the refresh")
        app.tabBars.buttons["Movimientos"].tap()
        XCTAssertTrue(element("movements.add", in: app).waitForExistence(timeout: 10))
        let first = text("Supermercado", in: app)
        XCTAssertTrue(first.waitForExistence(timeout: 10), "a movement")
        pull(app)
        sleep(1)
        XCTAssertTrue(text("Supermercado", in: app).waitForExistence(timeout: 10), "Movimientos after the refresh")
        XCTAssertFalse(element("app.notice", in: app).exists)
    }
}
