import XCTest

/// JARVIS agenda (J2) on the fixture backend: the Owner's upcoming events (populated: two), the empty
/// state, "Agendar con JARVIS", and an event confirmed in the chat reaching the agenda. Other roles
/// never reach JARVIS (JarvisAccessUITests). Android: `JarvisAgendaUiTest`.
@MainActor
final class JarvisAgendaUITests: XCTestCase {
    private func launchOwner(_ scenario: String = "populated") -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", scenario, "-DincrSkipLogin", "-DincrTab", "profile", "-DincrRole", "owner",
                               "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        app.launch()
        return app
    }

    private func element(_ identifier: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any)[identifier].firstMatch
    }

    private func text(_ content: String, in app: XCUIApplication) -> XCUIElement {
        app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", content)).firstMatch
    }

    private func openAgenda(_ app: XCUIApplication) {
        let entry = element("profile.jarvis", in: app)
        XCTAssertTrue(entry.waitForExistence(timeout: 5))
        entry.tap()
        let agenda = element("jarvis.section.calendar", in: app)
        XCTAssertTrue(agenda.waitForExistence(timeout: 5))
        agenda.tap()
    }

    func testOwnerSeesTheUpcomingEvents() {
        let app = launchOwner()
        openAgenda(app)
        XCTAssertTrue(text("Reunión con el contador", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("Cita médica", in: app).exists)
        XCTAssertTrue(text("10:00", in: app).exists)
        XCTAssertTrue(element("jarvis.agenda.schedule", in: app).exists)
    }

    func testAnEmptyAgendaSaysSoAndOffersJarvis() {
        let app = launchOwner("empty")
        openAgenda(app)
        XCTAssertTrue(element("jarvis.agenda.empty", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("No hay compromisos próximos", in: app).exists)
        element("jarvis.agenda.schedule", in: app).tap()
        XCTAssertTrue(element("jarvis.chat.input", in: app).waitForExistence(timeout: 5))
    }

    func testAnEventConfirmedInTheChatReachesTheAgenda() {
        let app = launchOwner()
        openAgenda(app)
        XCTAssertTrue(text("Reunión con el contador", in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(text("dentista", in: app).exists)
        element("jarvis.agenda.schedule", in: app).tap()
        let input = element("jarvis.chat.input", in: app)
        XCTAssertTrue(input.waitForExistence(timeout: 5))
        input.tap()
        input.typeText("Agendá dentista el 10 de octubre a las 3pm")
        element("jarvis.chat.send", in: app).tap()
        let confirm = element("jarvis.chat.confirm", in: app)
        XCTAssertTrue(confirm.waitForExistence(timeout: 10))
        confirm.tap()
        XCTAssertTrue(text("Guardé en calendario", in: app).waitForExistence(timeout: 10))
        // Back to the agenda: it reloads and shows the confirmed event.
        app.navigationBars.buttons.element(boundBy: 0).tap()
        XCTAssertTrue(text("dentista", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(text("15:00", in: app).exists)
    }
}
