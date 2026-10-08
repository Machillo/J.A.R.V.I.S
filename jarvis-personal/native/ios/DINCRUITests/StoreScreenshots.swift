import XCTest

/// App Store screenshots (jarvis-personal/store-assets/CAPTURE.md). Opt-in: runs only when the
/// test runner gets `DINCR_STORE_SHOTS_DIR` (pass `TEST_RUNNER_DINCR_STORE_SHOTS_DIR=<dir>` to
/// xcodebuild), so the regular UI-test run skips it.
///
/// Each test opens the real app on the STORE sample (`-DincrFixtures store`, Debug only) with the
/// screen's plan (store-assets/config/screens.json), navigates like a user, waits for the loaded
/// content and writes `<dir>/<es|en>/<DINCR_STORE_DEVICE: phone|tablet>/<id>.png`. The engine
/// screens (Home VIP, budget, strategy) show the backend engines' own answers (StoreSample).
@MainActor
final class StoreScreenshots: XCTestCase {
    private struct Language: Sendable {
        let id: String, languages: String, locale: String, spanish: Bool
        func pick(_ spanishText: String, _ englishText: String) -> String { spanish ? spanishText : englishText }
    }

    private static let languages = [
        Language(id: "es", languages: "(es)", locale: "es_CR", spanish: true),
        Language(id: "en", languages: "(en)", locale: "en_US", spanish: false),
    ]

    /// The output folder, or a skip when the run did not ask for store screenshots.
    private func outputFolder(_ language: Language) throws -> URL {
        let environment = ProcessInfo.processInfo.environment
        let dir = environment["DINCR_STORE_SHOTS_DIR"] ?? ""
        try XCTSkipIf(dir.isEmpty, "store screenshots are opt-in (DINCR_STORE_SHOTS_DIR)")
        let device = environment["DINCR_STORE_DEVICE"] == "tablet" ? "tablet" : "phone"
        return URL(fileURLWithPath: dir).appendingPathComponent(language.id).appendingPathComponent(device)
    }

    private func launch(_ language: Language, plan: String) throws -> XCUIApplication {
        _ = try outputFolder(language)
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "store", "-DincrSkipLogin", "-DincrPlan", plan,
                               "-AppleLanguages", language.languages, "-AppleLocale", language.locale]
        app.launch()
        return app
    }

    private func wait(_ app: XCUIApplication, _ text: String) {
        let element = app.staticTexts[text].exists ? app.staticTexts[text] : app.descendants(matching: .any)[text]
        XCTAssertTrue(element.waitForExistence(timeout: 15), "missing \"\(text)\"")
    }

    private func open(_ app: XCUIApplication, _ identifier: String) {
        let element = app.descendants(matching: .any)[identifier].firstMatch
        XCTAssertTrue(element.waitForExistence(timeout: 15), "missing \(identifier)")
        element.tap()
    }

    private func tab(_ app: XCUIApplication, _ title: String) {
        // iPhone: the tab bar. iPad (iOS 18+): the tabs sit in the top bar, outside any tab bar.
        // iOS 26+ can expose a tab twice (the item and its selection lens): tap the first. Each test
        // then waits for its destination's content, so a wrong tap fails instead of capturing.
        let inTabBar = app.tabBars.buttons[title].firstMatch
        let button = inTabBar.waitForExistence(timeout: 5) ? inTabBar : app.buttons[title].firstMatch
        XCTAssertTrue(button.waitForExistence(timeout: 15), "missing tab \(title)")
        button.tap()
    }

    private func capture(_ id: String, _ language: Language) throws {
        sleep(1) // let the last transition settle
        let folder = try outputFolder(language)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        try XCUIScreen.main.screenshot().pngRepresentation.write(to: folder.appendingPathComponent("\(id).png"))
    }

    private func shoot(_ id: String, plan: String, _ steps: (XCUIApplication, Language) -> Void) throws {
        for language in Self.languages {
            let app = try launch(language, plan: plan)
            steps(app, language)
            try capture(id, language)
            app.terminate()
        }
    }

    func testS01Home() throws {
        try shoot("01-home", plan: "vip") { app, l in
            self.wait(app, l.pick("Podés gastar con tranquilidad", "Safe to spend"))
            self.wait(app, l.pick("Qué sigue", "What’s next"))
        }
    }

    func testS02Overview() throws {
        try shoot("02-overview", plan: "free") { app, l in
            self.wait(app, l.pick("Resultado del mes", "This month’s result"))
            self.wait(app, l.pick("Accesos rápidos", "Quick access"))
        }
    }

    func testS03Movements() throws {
        try shoot("03-movements", plan: "free") { app, l in
            self.wait(app, l.pick("Resultado del mes", "This month’s result"))
            self.tab(app, l.pick("Movimientos", "Transactions"))
            self.wait(app, l.pick("Café", "Coffee"))
        }
    }

    func testS04Debts() throws {
        try shoot("04-debts", plan: "free") { app, l in
            self.open(app, "home.debts") // debts live on Hoy
            self.wait(app, l.pick("Préstamo del carro", "Car loan"))
        }
    }

    func testS05Goals() throws {
        try shoot("05-goals", plan: "free") { app, l in
            self.open(app, "home.goals") // goals live on Hoy
            self.wait(app, l.pick("Vacaciones", "Vacation"))
        }
    }

    func testS06Budget() throws {
        try shoot("06-budget", plan: "basic") { app, l in
            self.tab(app, l.pick("Perfil", "Profile"))
            self.open(app, "profile.budget") // Perfil → Finanzas
            self.wait(app, l.pick("Total presupuestado", "Total budgeted"))
            self.wait(app, "budget.edit")
        }
    }

    func testS07Strategy() throws {
        try shoot("07-strategy", plan: "basic") { app, l in
            self.tab(app, "Plan")
            self.open(app, "plan.strategy")
            self.wait(app, l.pick("Libre después de tus compromisos", "Left after your commitments"))
        }
    }

    func testS08Mail() throws {
        try shoot("08-mail", plan: "vip") { app, l in
            self.tab(app, l.pick("Perfil", "Profile"))
            self.open(app, "profile.mail")
            self.wait(app, l.pick("Por revisar", "To review"))
        }
    }
}
