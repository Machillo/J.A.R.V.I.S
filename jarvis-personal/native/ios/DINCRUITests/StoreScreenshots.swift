import XCTest

/// App Store screenshots (jarvis-personal/store-assets/CAPTURE.md). Opt-in: runs only when the
/// test runner gets `DINCR_STORE_SHOTS_DIR` (pass `TEST_RUNNER_DINCR_STORE_SHOTS_DIR=<dir>` to
/// xcodebuild), so the regular UI-test run skips it.
///
/// Each test opens the real app on the STORE sample (`-DincrFixtures store`, Debug only) with the
/// Free plan, navigates like a user, waits for the loaded content and writes the screen to
/// `<dir>/<es|en>/<DINCR_STORE_DEVICE: phone|tablet>/<id>.png`. Only screens the native iOS app
/// really has are captured: Home, Transactions and the Plan hub (debts and goals).
@MainActor
final class StoreScreenshots: XCTestCase {
    private struct Language {
        let id: String, languages: String, locale: String
        let pick: (String, String) -> String
    }

    private let languages = [
        Language(id: "es", languages: "(es)", locale: "es_CR") { spanish, _ in spanish },
        Language(id: "en", languages: "(en)", locale: "en_US") { _, english in english },
    ]

    /// The output folder, or a skip when the run did not ask for store screenshots.
    private func outputFolder(_ language: Language) throws -> URL {
        let environment = ProcessInfo.processInfo.environment
        let dir = environment["DINCR_STORE_SHOTS_DIR"] ?? ""
        try XCTSkipIf(dir.isEmpty, "store screenshots are opt-in (DINCR_STORE_SHOTS_DIR)")
        let device = environment["DINCR_STORE_DEVICE"] == "tablet" ? "tablet" : "phone"
        return URL(fileURLWithPath: dir).appendingPathComponent(language.id).appendingPathComponent(device)
    }

    private func launch(_ language: Language) throws -> XCUIApplication {
        _ = try outputFolder(language)
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "store", "-DincrSkipLogin", "-DincrPlan", "free",
                               "-AppleLanguages", language.languages, "-AppleLocale", language.locale]
        app.launch()
        return app
    }

    private func wait(_ app: XCUIApplication, _ text: String) {
        XCTAssertTrue(app.staticTexts[text].waitForExistence(timeout: 15), "missing \"\(text)\"")
    }

    private func capture(_ id: String, _ language: Language) throws {
        sleep(1) // let the last transition settle
        let folder = try outputFolder(language)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        try XCUIScreen.main.screenshot().pngRepresentation.write(to: folder.appendingPathComponent("\(id).png"))
    }

    func testS02Overview() throws {
        for language in languages {
            let app = try launch(language)
            wait(app, language.pick("Disponible este mes", "Available this month"))
            wait(app, language.pick("Ingresos y gastos", "Income and expenses"))
            try capture("02-overview", language)
            app.terminate()
        }
    }

    func testS03Movements() throws {
        for language in languages {
            let app = try launch(language)
            wait(app, language.pick("Disponible este mes", "Available this month"))
            app.tabBars.buttons[language.pick("Movimientos", "Transactions")].tap()
            wait(app, language.pick("Café", "Coffee"))
            try capture("03-movements", language)
            app.terminate()
        }
    }

    func testS04Debts() throws {
        for language in languages {
            let app = try launch(language)
            wait(app, language.pick("Disponible este mes", "Available this month"))
            app.tabBars.buttons[language.pick("Plan", "Plan")].tap()
            wait(app, language.pick("Préstamo del carro", "Car loan"))
            try capture("04-debts", language)
            app.terminate()
        }
    }
}
