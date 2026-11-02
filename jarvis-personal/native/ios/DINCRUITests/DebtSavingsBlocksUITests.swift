import XCTest

/// DB-1 — Plan → Ahorro para deudas: the Owner reads the strategy's next locked saving, records the one
/// he created at the bank and sees it with its progress; no plan sees the row. Android twin:
/// `DebtSavingsBlocksUiTest`. Fixture data only.
@MainActor
final class DebtSavingsBlocksUITests: XCTestCase {
    private func launch(plan: String?, role: String? = nil) -> XCUIApplication {
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrTab", "plan",
                         "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        if let plan { arguments += ["-DincrPlan", plan] }
        if let role { arguments += ["-DincrRole", role] }
        app.launchArguments = arguments
        app.launch()
        return app
    }

    private func element(_ id: String, in app: XCUIApplication) -> XCUIElement { app.descendants(matching: .any)[id].firstMatch }

    private func reveal(_ id: String, in app: XCUIApplication) -> XCUIElement {
        let target = element(id, in: app)
        for _ in 0..<6 where !(target.waitForExistence(timeout: 2) && target.isHittable) { app.swipeUp() }
        return target
    }

    func testTheOwnerRecordsTheProposedSavingAndSeesItsProgress() {
        let app = launch(plan: "vip", role: "owner")
        reveal("plan.debtBlocks", in: app).tap()
        let headline = element("debtBlocks.headline", in: app)
        XCTAssertTrue(headline.waitForExistence(timeout: 10))
        XCTAssertTrue(headline.label.contains("cada jueves por 6 meses"), headline.label)
        reveal("debtBlocks.create", in: app).tap()
        let save = element("debtBlocks.save", in: app)
        XCTAssertTrue(save.waitForExistence(timeout: 10))
        save.tap()
        // Recorded: the debt is taken, so nothing is left to lock, and the block shows its progress.
        let status = element("debtBlocks.status", in: app)
        XCTAssertTrue(status.waitForExistence(timeout: 10))
        XCTAssertTrue(status.label.contains("ya usan todo tu sobrante"), status.label)
        XCTAssertTrue(reveal("debtBlocks.block.fixture-block-1", in: app).exists)
    }

    func testAMaturedSavingIsPaidIntoItsDebtAndLeavesTheList() {
        let app = launch(plan: "vip", role: "owner")
        reveal("plan.debtBlocks", in: app).tap()
        reveal("debtBlocks.pay.fixture-matured-1", in: app).tap()
        let save = element("debtBlocks.applySave", in: app)
        XCTAssertTrue(save.waitForExistence(timeout: 10))
        // The bank shortened the term: the installments left, as the bank says them.
        let remaining = element("debtBlocks.remaining", in: app)
        XCTAssertTrue(remaining.waitForExistence(timeout: 5))
        remaining.tap()
        remaining.typeText("12")
        save.tap()
        let notice = element("debtBlocks.notice", in: app)
        XCTAssertTrue(notice.waitForExistence(timeout: 10))
        XCTAssertTrue(notice.label.contains("Listo"), notice.label)
        XCTAssertFalse(element("debtBlocks.block.fixture-matured-1", in: app).exists)
    }

    func testAnExtraPaymentWaitsForTheBankAndIsAnsweredLater() {
        let app = launch(plan: "vip")
        reveal("plan.debts", in: app).tap()
        let pay = element("debt.pay.31", in: app)
        XCTAssertTrue(pay.waitForExistence(timeout: 10))
        pay.tap()
        let field = element("amount.field", in: app)
        XCTAssertTrue(field.waitForExistence(timeout: 10))
        field.tap()
        field.typeText("100000")                     // above the ₡45.000 installment
        element("amount.bank", in: app).tap()
        let later = app.buttons["El banco me avisa después"].firstMatch
        XCTAssertTrue(later.waitForExistence(timeout: 5))
        later.tap()
        app.buttons["amount.save"].tap()
        XCTAssertTrue(element("debts.waitingForBank", in: app).waitForExistence(timeout: 10), "the debt waits for the bank")
        reveal("debts.afterExtra.31", in: app).tap()
        let remaining = element("debts.afterExtra.remaining", in: app)
        XCTAssertTrue(remaining.waitForExistence(timeout: 10))
        remaining.tap()
        remaining.typeText("6")
        element("debts.afterExtra.save", in: app).tap()
        XCTAssertTrue(element("plan.notice", in: app).waitForExistence(timeout: 10))
        XCTAssertFalse(element("debts.waitingForBank", in: app).exists, "answered: nothing is waiting")
    }

    func testNoPlanSeesTheRow() {
        for plan in [nil, "basic", "vip"] as [String?] {
            let app = launch(plan: plan)
            XCTAssertTrue(element("plan.debts", in: app).waitForExistence(timeout: 10))
            XCTAssertFalse(element("plan.debtBlocks", in: app).exists, plan ?? "free")
            app.terminate()
        }
    }
}
