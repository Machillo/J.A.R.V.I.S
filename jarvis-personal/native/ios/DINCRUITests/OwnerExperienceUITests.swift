import XCTest

/// The Owner's native experience (DINCR Owner redesign) on the fixture backend: the Owner's Today
/// (money, attention, agenda, JARVIS), the chat's deliberate scope, the agenda reached from Today,
/// the largest text size, and that no other account ever sees Owner UI. Synthetic data only.
///
/// Opt-in screenshots: with `TEST_RUNNER_DINCR_OWNER_SHOTS_DIR=<dir>` the screenshot test writes
/// `<dir>/<dark|light>/<id>.png` (CI uploads them as an artifact for design review).
@MainActor
final class OwnerExperienceUITests: XCTestCase {
    private func launch(role: String? = "owner", plan: String? = "vip", scenario: String = "populated", tab: String? = nil,
                        appearance: String? = nil, extra: [String] = []) -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        var arguments: [String] = ["-DincrDisableAnimations", "-DincrFixtures", scenario, "-DincrSkipLogin",
                                   "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        if let role { arguments += ["-DincrRole", role] }
        if let plan { arguments += ["-DincrPlan", plan] }
        if let tab { arguments += ["-DincrTab", tab] }
        if let appearance { arguments += ["-dincr.appearance", appearance] }
        arguments += extra
        app.launchArguments = arguments
        app.launch()
        return app
    }

    private func element(_ identifier: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any)[identifier].firstMatch
    }

    private func text(_ content: String, in app: XCUIApplication) -> XCUIElement {
        app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", content)).firstMatch
    }

    /// Scrolls until the element can be tapped (Today is longer than one screen at large sizes).
    /// It scrolls toward the element: back up when it sits above the visible area (e.g. after
    /// returning from a screen opened near the bottom), down otherwise. At most 8 swipes.
    @discardableResult
    private func reveal(_ identifier: String, in app: XCUIApplication) -> XCUIElement {
        let target = element(identifier, in: app)
        XCTAssertTrue(target.waitForExistence(timeout: 10), "missing \(identifier)")
        let viewport = app.windows.firstMatch.frame
        for _ in 0..<8 where !target.isHittable {
            if target.frame.midY < viewport.midY { app.swipeDown() } else { app.swipeUp() }
        }
        XCTAssertTrue(target.isHittable, "\(identifier) is not reachable")
        return target
    }

    // MARK: Today

    func testOwnerTodayAnswersMoneyAttentionAgendaAndJarvis() {
        let app = launch()
        XCTAssertTrue(element("owner.home", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(element("owner.home.status", in: app).waitForExistence(timeout: 10), "the backend's key figure")
        XCTAssertTrue((element("owner.home.greeting", in: app).label).contains("Ana."), "the greeting uses the profile's first name")
        XCTAssertTrue(element("owner.home.jarvis.mark", in: app).exists)
        // Para atender (UX-5): the command center's alerts in the backend's words, high first, and
        // "Ver todas" because there are more than three.
        reveal("owner.home.attention.item.center", in: app)
        XCTAssertTrue(text("Reserva menor a un mes", in: app).exists)
        XCTAssertTrue(text("Pago de tarjeta en 5 días", in: app).exists)
        XCTAssertTrue(element("owner.home.attention.all", in: app).exists)
        // Next: the JARVIS agenda, next event first.
        reveal("owner.home.agenda.event", in: app)
        XCTAssertTrue(text("Reunión con el contador", in: app).exists)
        reveal("owner.home.jarvis.chat", in: app)
        XCTAssertTrue(element("owner.home.jarvis.agenda", in: app).exists)
    }

    func testOwnerTodayOpensTheChatTheAgendaAndTheMailReview() {
        let app = launch()
        reveal("owner.home.jarvis.chat", in: app).tap()
        XCTAssertTrue(element("jarvis.chat.input", in: app).waitForExistence(timeout: 5))
        app.navigationBars.buttons.element(boundBy: 0).tap()
        reveal("owner.home.jarvis.agenda", in: app).tap()
        XCTAssertTrue(text("Cita médica", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(element("jarvis.agenda.schedule", in: app).exists)
        app.navigationBars.buttons.element(boundBy: 0).tap()
        // The mail notices are the fourth item: "Ver todas" → their link opens the Email Monitor.
        reveal("owner.home.attention.all", in: app).tap()
        reveal("attention.link.review", in: app).tap()
        XCTAssertTrue(text("Por revisar", in: app).waitForExistence(timeout: 10), "the Email Monitor's review list")
    }

    func testOwnerTodayReachesDebtsAndGoals() {
        // Debts and goals left the Plan tab for Today (#302); the Owner's own Today (#303) keeps them,
        // opening the same screens the other plans reach from theirs.
        let app = launch()
        XCTAssertTrue(element("owner.home", in: app).waitForExistence(timeout: 10))
        reveal("owner.home.debts", in: app).tap()
        XCTAssertTrue(app.navigationBars["Deudas"].waitForExistence(timeout: 10), "the debts screen")
        app.navigationBars.buttons.element(boundBy: 0).tap()
        reveal("owner.home.goals", in: app).tap()
        XCTAssertTrue(app.navigationBars["Metas y ahorro"].waitForExistence(timeout: 10), "the goals screen")
        // UX-4: debts are managed in Plan → Deudas too (Today keeps its shortcut); goals stay on Today.
        app.navigationBars.buttons.element(boundBy: 0).tap()
        app.tabBars.buttons["Plan"].tap()
        XCTAssertTrue(element("plan.strategy", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(element("plan.debts", in: app).exists)
        XCTAssertFalse(element("plan.goals", in: app).exists)
    }

    func testAnEmptyAgendaOnTodayOffersJarvis() {
        let app = launch(scenario: "empty")
        reveal("owner.home.agenda.empty", in: app).tap()
        XCTAssertTrue(element("jarvis.chat.input", in: app).waitForExistence(timeout: 5))
    }

    func testOtherAccountsKeepTheirTodayAndNeverSeeOwnerUI() {
        for plan in [nil, "basic", "vip"] as [String?] {
            let app = launch(role: nil, plan: plan)
            let shown = element("home.status", in: app)
            XCTAssertTrue(shown.waitForExistence(timeout: 10), plan ?? "free")
            XCTAssertFalse(element("owner.home", in: app).exists, plan ?? "free")
            XCTAssertFalse(element("owner.home.jarvis.mark", in: app).exists, plan ?? "free")
            app.terminate()
        }
    }

    func testOwnerTodayHoldsAtTheLargestTextSize() {
        let app = launch(extra: ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"])
        XCTAssertTrue(element("owner.home.status", in: app).waitForExistence(timeout: 10))
        // JARVIS comes first on the Owner's Hoy (UX-6); the financial blocks follow.
        reveal("owner.home.jarvis.chat", in: app).tap()
        XCTAssertTrue(element("jarvis.chat.input", in: app).waitForExistence(timeout: 5))
        // The quick actions wrap instead of disappearing.
        reveal("jarvis.chat.quick.overtime", in: app)
        app.navigationBars.buttons.element(boundBy: 0).tap()
        reveal("owner.home.attention.all", in: app)
    }

    // MARK: Chat scope

    func testTheChatOffersOnlyItsFourQuickActionsAndNeverSendsByItself() {
        let app = launch()
        reveal("owner.home.jarvis.chat", in: app).tap()
        XCTAssertTrue(element("jarvis.chat.empty", in: app).waitForExistence(timeout: 5))
        for action in ["overtime", "bonus", "schedule", "agenda"] {
            XCTAssertTrue(element("jarvis.chat.quick.\(action)", in: app).exists, action)
        }
        let quick = app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH %@", "jarvis.chat.quick."))
        XCTAssertEqual(Set((0..<quick.count).map { quick.element(boundBy: $0).identifier }).count, 4, "exactly the chat's scope")
        element("jarvis.chat.quick.overtime", in: app).tap()
        let input = element("jarvis.chat.input", in: app)
        XCTAssertTrue((input.value as? String ?? "").contains("Hoy hice"), "the phrase waits in the composer")
        XCTAssertFalse(element("jarvis.chat.owner", in: app).exists, "nothing is sent until the Owner sends it")
        XCTAssertFalse(element("jarvis.chat.confirm", in: app).exists)
        element("jarvis.chat.quick.agenda", in: app).tap()
        XCTAssertTrue(text("Reunión con el contador", in: app).waitForExistence(timeout: 10))
    }

    // MARK: Screenshots (opt-in)

    func testOwnerScreenshots() throws {
        let dir = ProcessInfo.processInfo.environment["DINCR_OWNER_SHOTS_DIR"] ?? ""
        try XCTSkipIf(dir.isEmpty, "Owner screenshots are opt-in (DINCR_OWNER_SHOTS_DIR)")
        for appearance in ["dark", "light"] {
            let folder = URL(fileURLWithPath: dir).appendingPathComponent(appearance)
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            func shot(_ id: String) throws {
                sleep(1)
                try XCUIScreen.main.screenshot().pngRepresentation.write(to: folder.appendingPathComponent("\(id).png"))
            }
            var app = launch(appearance: appearance)
            XCTAssertTrue(element("owner.home.status", in: app).waitForExistence(timeout: 10))
            XCTAssertTrue(element("owner.home.agenda.event", in: app).waitForExistence(timeout: 10))
            try shot("01-today")
            app.swipeUp()
            try shot("02-today-scrolled")
            reveal("owner.home.jarvis.chat", in: app).tap()
            XCTAssertTrue(element("jarvis.chat.empty", in: app).waitForExistence(timeout: 5))
            try shot("03-chat-empty")
            let input = element("jarvis.chat.input", in: app)
            input.tap()
            input.typeText("Hoy hice 3 horas extra")
            element("jarvis.chat.send", in: app).tap()
            XCTAssertTrue(element("jarvis.chat.confirm", in: app).waitForExistence(timeout: 10))
            try shot("04-chat-confirm")
            app.terminate()

            app = launch(tab: "profile", appearance: appearance)
            reveal("profile.jarvis", in: app).tap()
            XCTAssertTrue(element("jarvis.section.calendar", in: app).waitForExistence(timeout: 5))
            try shot("05-jarvis-hub")
            element("jarvis.section.calendar", in: app).tap()
            XCTAssertTrue(text("Reunión con el contador", in: app).waitForExistence(timeout: 10))
            try shot("06-agenda")
            app.navigationBars.buttons.element(boundBy: 0).tap()
            app.navigationBars.buttons.element(boundBy: 0).tap()
            XCTAssertTrue(element("profile.plan", in: app).waitForExistence(timeout: 5))
            try shot("07-profile")
            app.tabBars.buttons["Movimientos"].tap()
            sleep(2)
            try shot("08-movements")
            app.tabBars.buttons["Plan"].tap()
            sleep(2)
            try shot("09-plan")
            app.terminate()

            app = launch(scenario: "empty", tab: "profile", appearance: appearance)
            reveal("profile.jarvis", in: app).tap()
            element("jarvis.section.calendar", in: app).tap()
            XCTAssertTrue(element("jarvis.agenda.empty", in: app).waitForExistence(timeout: 10))
            try shot("10-agenda-empty")
            app.terminate()
        }
    }
}
