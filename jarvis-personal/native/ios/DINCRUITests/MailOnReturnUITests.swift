import XCTest

/// Mail recovery — when the app comes back to the foreground it reads the connected mailboxes and
/// Movimientos reads again: a purchase notice that arrived meanwhile appears without pulling to
/// refresh. Fixture data only (`-DincrMailArrives`: the second mail sync finds a new movement).
/// Reading mail is the Owner's alone during the launch: a VIP's app does not read on return.
/// Android twin: `MailOnReturnUiTest`.
@MainActor
final class MailOnReturnUITests: XCTestCase {
    private let arrived = "Compra detectada por correo"

    private func launch(role: String?) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrPlan", "vip",
                               "-DincrTab", "movements", "-DincrMailArrives", "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
            + (role.map { ["-DincrRole", $0] } ?? [])
        app.launch()
        return app
    }

    func testAPurchaseThatArrivedWhileAwayAppearsWhenTheAppComesBack() {
        let app = launch(role: "owner")
        let match = NSPredicate(format: "label CONTAINS %@", arrived)
        XCTAssertTrue(app.staticTexts["Salario quincenal"].waitForExistence(timeout: 10) ||
                      app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", "Movimientos")).firstMatch.exists)
        sleep(2)  // the launch sync has run; nothing new yet
        XCTAssertFalse(app.descendants(matching: .any).matching(match).firstMatch.exists, "not there before the notice arrives")

        XCUIDevice.shared.press(.home)
        sleep(2)
        app.activate()

        XCTAssertTrue(app.descendants(matching: .any).matching(match).firstMatch.waitForExistence(timeout: 15),
                      "the purchase appears on return, without a pull to refresh")
    }

    func testAVipsAppDoesNotReadMailOnReturn() {
        let app = launch(role: nil)
        let match = NSPredicate(format: "label CONTAINS %@", arrived)
        XCTAssertTrue(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", "Movimientos")).firstMatch.waitForExistence(timeout: 10))
        sleep(2)
        XCUIDevice.shared.press(.home)
        sleep(2)
        app.activate()
        sleep(4)  // longer than the Owner's case needs to show the purchase
        XCTAssertFalse(app.descendants(matching: .any).matching(match).firstMatch.exists, "no mail is read for a VIP")
    }
}
