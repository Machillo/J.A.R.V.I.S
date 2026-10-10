import XCTest

/// NAT-03 (B17 finding): a pull to refresh that fails on Hoy or Movimientos keeps what the screen
/// shows and says so in the app notice (read by VoiceOver), instead of replacing it with an error.
/// Android twin: `KeepContentUiTest`. Fixture data only; `-DincrRefreshFails` makes a read again
/// of Hoy's main source and of the movement list fail like an unreachable server.
final class KeepContentUITests: XCTestCase {
    private let failureNotice = "No pudimos actualizar. Seguís viendo la información anterior."

    private func launch(tab: String) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrTab", tab,
                               "-DincrRefreshFails", "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        app.launch()
        return app
    }

    private func element(_ id: String, in app: XCUIApplication) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }

    private func text(_ content: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", content)).firstMatch
    }

    private func pull(_ app: XCUIApplication) {
        let window = app.windows.firstMatch
        window.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.3))
            .press(forDuration: 0.05, thenDragTo: window.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.9)))
    }

    func testAFailedHoyRefreshKeepsHoyAndSaysSo() {
        let app = launch(tab: "home")
        XCTAssertTrue(element("home.today", in: app).waitForExistence(timeout: 10))
        pull(app)
        let notice = element("app.notice", in: app)
        XCTAssertTrue(notice.waitForExistence(timeout: 10), "the failure is said")
        XCTAssertEqual(notice.label, failureNotice)
        XCTAssertTrue(element("home.today", in: app).exists, "Hoy stays")
        XCTAssertFalse(app.buttons["Reintentar"].exists, "no error screen replaces Hoy")
    }

    func testAFailedMovementsRefreshKeepsTheList() {
        let app = launch(tab: "movements")
        XCTAssertTrue(text("Supermercado", in: app).waitForExistence(timeout: 10))
        pull(app)
        XCTAssertTrue(element("app.notice", in: app).waitForExistence(timeout: 10), "the failure is said")
        XCTAssertTrue(text("Supermercado", in: app).exists, "the list stays")
        XCTAssertFalse(app.buttons["Reintentar"].exists, "no error screen replaces the list")
    }
}
