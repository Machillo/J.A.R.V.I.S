import XCTest

/// SC-1 — Perfil → Atajos de iPhone on the fixture backend: VIP (and the Owner) activate and deactivate
/// the link; Free and Basic see the row locked with its plan, and it opens Suscripción.
final class ShortcutsSettingsUITests: XCTestCase {
    private func launch(plan: String? = nil, role: String? = nil) -> XCUIApplication {
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrTab", "profile",
                         "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        if let plan { arguments += ["-DincrPlan", plan] }
        if let role { arguments += ["-DincrRole", role] }
        app.launchArguments = arguments
        app.launch()
        return app
    }

    private func row(_ app: XCUIApplication) -> XCUIElement {
        let element = app.descendants(matching: .any)["profile.shortcuts"].firstMatch
        if !element.waitForExistence(timeout: 10) { app.swipeUp() }
        return element
    }

    private func status(_ app: XCUIApplication, is expected: String, file: StaticString = #filePath, line: UInt = #line) {
        let label = app.staticTexts["shortcuts.status"]
        let matches = NSPredicate(format: "label == %@", expected)
        let found = expectation(for: matches, evaluatedWith: label)
        XCTAssertEqual(XCTWaiter().wait(for: [found], timeout: 10), .completed, "status is \(label.exists ? label.label : "missing")", file: file, line: line)
    }

    func testVipActivatesAndDeactivates() {
        for (plan, role) in [("vip", nil), (nil, "owner")] as [(String?, String?)] {
            let app = launch(plan: plan, role: role)
            let entry = row(app)
            XCTAssertTrue(entry.waitForExistence(timeout: 5), role ?? plan ?? "")
            XCTAssertFalse(entry.label.contains("Disponible desde"), "shown locked: \(entry.label)")
            entry.tap()

            status(app, is: "No vinculado")
            app.buttons["shortcuts.activate"].tap()
            status(app, is: "Vinculado")
            XCTAssertTrue(app.buttons["shortcuts.deactivate"].waitForExistence(timeout: 5))
            app.buttons["shortcuts.deactivate"].tap()
            status(app, is: "No vinculado")
            XCTAssertTrue(app.buttons["shortcuts.activate"].waitForExistence(timeout: 5))
            XCTAssertFalse(app.staticTexts["shortcuts.error"].exists)
            app.terminate()
        }
    }

    func testFreeAndBasicSeeItLocked() {
        for plan in [nil, "basic"] as [String?] {
            let app = launch(plan: plan)
            let entry = row(app)
            XCTAssertTrue(entry.waitForExistence(timeout: 5), plan ?? "free")
            XCTAssertTrue(entry.label.contains("Disponible desde VIP"), "\(plan ?? "free"): not locked (\(entry.label))")
            entry.tap()
            XCTAssertFalse(app.staticTexts["shortcuts.status"].waitForExistence(timeout: 2), "the settings screen opened for \(plan ?? "free")")
            XCTAssertTrue(app.navigationBars["Suscripción"].waitForExistence(timeout: 5), "the locked row opens Suscripción")
            app.terminate()
        }
    }
}
