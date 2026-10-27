package com.dincr.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * A system shortcut (Android launcher shortcut, iOS App Shortcut / Back Tap) only asks the app to
 * open a screen; it never writes. The Swift twin is `QuickActionTests`.
 */
class QuickActionTest {
    @Test fun newExpenseHasAStableRouteAndIntentAction() {
        assertEquals("new_expense", QuickAction.NEW_EXPENSE.route)
        assertEquals(QuickAction.NEW_EXPENSE, QuickAction.fromRoute("new_expense"))
        assertEquals(QuickAction.NEW_EXPENSE, QuickAction.fromIntentAction(QuickAction.NEW_EXPENSE.intentAction))
    }

    @Test fun unknownRoutesAndActionsAreNotQuickActions() {
        listOf("mail", "", "NEW_EXPENSE", "new_income").forEach { assertNull(QuickAction.fromRoute(it)) }
        listOf(null, "android.intent.action.MAIN", "android.intent.action.VIEW", "com.dincr.app.action.DELETE").forEach {
            assertNull(QuickAction.fromIntentAction(it))
        }
    }
}
