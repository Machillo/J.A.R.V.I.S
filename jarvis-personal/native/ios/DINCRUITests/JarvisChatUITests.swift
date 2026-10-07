import XCTest

/// JARVIS chat (J1) on the fixture backend, whose scripted chat (`FixtureBackend.jarvisChat`) shows
/// a payroll change for "horas extra", fails for "falla" and answers anything else plainly.
/// Only the Owner reaches the chat (JarvisAccessUITests covers the other roles). Android: `JarvisChatUiTest`.
@MainActor
final class JarvisChatUITests: XCTestCase {
    private func launchOwnerChat(skipLogin: Bool = true) -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrTab", "profile", "-DincrRole", "owner",
                               "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"] + (skipLogin ? ["-DincrSkipLogin"] : [])
        app.launch()
        return app
    }

    private func element(_ identifier: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any)[identifier].firstMatch
    }

    private func openChat(_ app: XCUIApplication) {
        let entry = element("profile.jarvis", in: app)
        XCTAssertTrue(entry.waitForExistence(timeout: 5))
        entry.tap()
        let chat = element("jarvis.section.chat", in: app)
        XCTAssertTrue(chat.waitForExistence(timeout: 5))
        chat.tap()
        XCTAssertTrue(element("jarvis.chat.input", in: app).waitForExistence(timeout: 5))
    }

    /// A chat bubble. Its accessibility label names the speaker ("Vos: …" / "JARVIS: …"), so it is
    /// matched by content, never by the exact label.
    private func bubble(_ text: String, in app: XCUIApplication) -> XCUIElement {
        app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", text)).firstMatch
    }

    private func send(_ text: String, in app: XCUIApplication) {
        let input = element("jarvis.chat.input", in: app)
        input.tap()
        input.typeText(text)
        element("jarvis.chat.send", in: app).tap()
    }

    func testOwnerAsksAndGetsAnAnswer() {
        let app = launchOwnerChat()
        openChat(app)
        XCTAssertTrue(element("jarvis.chat.empty", in: app).exists)
        send("¿Cuál es mi deuda más alta?", in: app)
        XCTAssertTrue(bubble("¿Cuál es mi deuda más alta?", in: app).waitForExistence(timeout: 5))
        XCTAssertTrue(bubble("Señor, esto es una respuesta de ejemplo.", in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(element("jarvis.chat.confirm", in: app).exists, "a plain answer asks for nothing")
    }

    func testAChangeIsShownFirstAndSavedOnConfirm() {
        let app = launchOwnerChat()
        openChat(app)
        send("Hoy hice 3 horas extra", in: app)
        let confirm = element("jarvis.chat.confirm", in: app)
        XCTAssertTrue(confirm.waitForExistence(timeout: 10))
        XCTAssertTrue(element("jarvis.chat.cancel", in: app).exists)
        XCTAssertTrue(bubble("₡9,000.00", in: app).exists, "the amount is shown before saving")
        confirm.tap()
        XCTAssertTrue(bubble("Señor, OT registrado", in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(element("jarvis.chat.confirm", in: app).exists)
    }

    func testAnAmbiguousAnswerIsAskedAboutAndTheAnswerContinues() {
        let app = launchOwnerChat()
        openChat(app)
        send("quiero crear una meta", in: app)
        XCTAssertTrue(bubble("¿Cómo se llama la meta?", in: app).waitForExistence(timeout: 10))
        send("Fondo de emergencia", in: app)
        let answer = element("jarvis.chat.clarify.answer", in: app)
        XCTAssertTrue(answer.waitForExistence(timeout: 10))
        XCTAssertTrue(element("jarvis.chat.clarify.other", in: app).exists)
        answer.tap()
        XCTAssertTrue(bubble("¿Cuál es el monto objetivo de la meta?", in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(element("jarvis.chat.clarify.answer", in: app).exists)
    }

    func testAnotherQuestionKeepsThePendingOne() {
        let app = launchOwnerChat()
        openChat(app)
        send("quiero crear una meta", in: app)
        XCTAssertTrue(bubble("¿Cómo se llama la meta?", in: app).waitForExistence(timeout: 10))
        send("Fondo de emergencia", in: app)
        let other = element("jarvis.chat.clarify.other", in: app)
        XCTAssertTrue(other.waitForExistence(timeout: 10))
        other.tap()
        XCTAssertTrue(bubble("Señor, este es su análisis financiero.", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(bubble("Tenés una pregunta pendiente", in: app).exists)
    }

    func testCancelSavesNothing() {
        let app = launchOwnerChat()
        openChat(app)
        send("Hoy hice 3 horas extra", in: app)
        let cancel = element("jarvis.chat.cancel", in: app)
        XCTAssertTrue(cancel.waitForExistence(timeout: 10))
        cancel.tap()
        XCTAssertTrue(bubble("Listo, cancelé el registro. No guardé nada.", in: app).waitForExistence(timeout: 10))
    }

    func testAFailedMessageOffersRetry() {
        let app = launchOwnerChat()
        openChat(app)
        send("esto falla", in: app)
        let retry = element("jarvis.chat.retry", in: app)
        XCTAssertTrue(retry.waitForExistence(timeout: 10))
        XCTAssertTrue(element("jarvis.chat.failed", in: app).exists)
        // The chat stays usable: another message goes through.
        send("hola", in: app)
        XCTAssertTrue(bubble("Señor, esto es una respuesta de ejemplo.", in: app).waitForExistence(timeout: 10))
    }

    func testAnUnexpectedAnswerDoesNotCrash() {
        let app = launchOwnerChat()
        openChat(app)
        send("respuesta rara", in: app)
        XCTAssertTrue(element("jarvis.chat.failed", in: app).waitForExistence(timeout: 10))
        XCTAssertTrue(element("jarvis.chat.input", in: app).exists)
    }

    func testSigningOutForgetsTheConversation() {
        let app = launchOwnerChat(skipLogin: false)
        let google = app.buttons["login.google"]
        XCTAssertTrue(google.waitForExistence(timeout: 5))
        google.tap()
        openChat(app)
        send("hola", in: app)
        XCTAssertTrue(bubble("Señor, esto es una respuesta de ejemplo.", in: app).waitForExistence(timeout: 10))
        // Back to the Profile hub (chat → JARVIS → Profile), sign out and in again: the chat starts empty.
        for _ in 0..<2 { app.navigationBars.buttons.element(boundBy: 0).tap() }
        let signOut = element("profile.signOut", in: app)
        XCTAssertTrue(element("profile.plan", in: app).waitForExistence(timeout: 5))
        for _ in 0..<6 where !(signOut.exists && signOut.isHittable) { app.swipeUp() }
        signOut.tap()
        let sheetButton = app.sheets.buttons["Cerrar sesión"]
        if sheetButton.waitForExistence(timeout: 3) {
            sheetButton.tap()
        } else {
            app.buttons.matching(NSPredicate(format: "label == %@ AND identifier != %@", "Cerrar sesión", "profile.signOut")).firstMatch.tap()
        }
        XCTAssertTrue(google.waitForExistence(timeout: 5))
        google.tap()
        openChat(app)
        XCTAssertTrue(element("jarvis.chat.empty", in: app).exists)
        XCTAssertFalse(bubble("hola", in: app).exists)
    }
}
