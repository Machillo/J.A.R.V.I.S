import Testing
@testable import DincrCore

/// A system shortcut (iOS App Shortcut / Back Tap, Android launcher shortcut) only asks the app to
/// open a screen; it never writes (Android: `QuickActionTest`).
@Suite struct QuickActionTests {
    @Test func newExpenseHasAStableRoute() {
        #expect(QuickAction.newExpense.route == "new_expense")
        #expect(QuickAction(route: "new_expense") == .newExpense)
    }

    @Test func unknownRoutesAreNotQuickActions() {
        // The mail return keeps its own route; nothing else becomes a quick action.
        for route in ["mail", "", "NEW_EXPENSE", "new_income"] {
            #expect(QuickAction(route: route) == nil)
        }
    }

    @Test func aLaunchArgumentRequestsOne() {
        #expect(QuickAction.fromLaunchArguments(["App", "-DincrQuickAction", "new_expense"]) == .newExpense)
        #expect(QuickAction.fromLaunchArguments(["App", "-DincrQuickAction"]) == nil)
        #expect(QuickAction.fromLaunchArguments(["App", "-DincrQuickAction", "delete_everything"]) == nil)
        #expect(QuickAction.fromLaunchArguments(["App"]) == nil)
    }
}
