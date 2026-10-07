import XCTest

/// JARVIS role matrix on the fixture backend (roadmap J0): only the Owner's role in `/auth/me`
/// opens JARVIS; Free, Basic, VIP and admin never see it, and the Owner keeps every DINCR screen.
/// The fixture server's role comes from `-DincrRole` (Debug fixtures only). Android: `JarvisAccessUiTest`.
@MainActor
final class JarvisAccessUITests: XCTestCase {
    private func launch(role: String? = nil, plan: String? = nil) -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrTab", "profile",
                               "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
            + (role.map { ["-DincrRole", $0] } ?? []) + (plan.map { ["-DincrPlan", $0] } ?? [])
        app.launch()
        return app
    }

    private func element(_ identifier: String, in app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any)[identifier].firstMatch
    }

    func testOwnerGetsJarvisWithTheFiveFinalTabs() {
        let app = launch(role: "owner")
        let entry = element("profile.jarvis", in: app)
        XCTAssertTrue(entry.waitForExistence(timeout: 5))
        // UX-13: the Owner has the five final tabs (no DINCR tab), VIP screens such as the Email Monitor, and JARVIS in Perfil.
        for tab in ["Hoy", "Movimientos", "Plan", "Patrimonio", "Perfil"] { XCTAssertTrue(app.tabBars.buttons[tab].exists, tab) }
        XCTAssertFalse(app.tabBars.buttons["DINCR"].exists)
        XCTAssertTrue(element("profile.mail", in: app).exists)
        entry.tap()
        let memory = element("jarvis.section.memory", in: app)
        XCTAssertTrue(memory.waitForExistence(timeout: 5))
        XCTAssertTrue(element("jarvis.section.chat", in: app).exists)
        memory.tap()
        // A section not ported yet says so and shows no sample content.
        XCTAssertTrue(element("jarvis.restoring", in: app).waitForExistence(timeout: 5))
    }

    func testFreeBasicAndVipNeverSeeJarvis() {
        for plan in [nil, "basic", "vip"] as [String?] {
            let app = launch(plan: plan)
            XCTAssertTrue(element("profile.subscription", in: app).waitForExistence(timeout: 5), plan ?? "free")
            XCTAssertFalse(element("profile.jarvis", in: app).exists, plan ?? "free")
            app.terminate()
        }
    }

    func testAdminGetsNeitherThePublicAppNorJarvis() {
        let app = launch(role: "admin", plan: "vip")
        XCTAssertTrue(app.staticTexts["Esta cuenta no está disponible en DINCR"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.tabBars.firstMatch.exists)
        XCTAssertFalse(element("profile.jarvis", in: app).exists)
    }

    func testTheRoleIsReadFromTheServerOnEveryLaunch() {
        // Nothing about the Owner survives on the device: the next session's /auth/me decides.
        let owner = launch(role: "owner")
        XCTAssertTrue(element("profile.jarvis", in: owner).waitForExistence(timeout: 5))
        owner.terminate()
        let user = launch(plan: "vip")
        XCTAssertTrue(element("profile.subscription", in: user).waitForExistence(timeout: 5))
        XCTAssertFalse(element("profile.jarvis", in: user).exists)
    }
}
