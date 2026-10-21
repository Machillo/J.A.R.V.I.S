package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isSelectable
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.performSemanticsAction
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import com.dincr.data.FAKE_ARRIVED_MOVEMENT
import com.dincr.data.FakeBackend
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * Mail recovery — when the app comes back to the foreground it reads the connected mailboxes (VIP and
 * the Owner) and Movimientos reads again: a purchase notice that arrived meanwhile appears without
 * pulling to refresh. Free and Basic have no mail and never call the sync. iOS twin:
 * `MailOnReturnUITests`. FakeBackend only ([FakeBackend.mailArrives]).
 */
class MailOnReturnUiTest {
    @get:Rule val compose = createEmptyComposeRule()
    private var scenario: ActivityScenario<MainActivity>? = null

    @After fun close() { scenario?.close() }

    private fun present(text: String) = compose.onAllNodes(hasText(text, substring = true), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    private fun waitUntil(what: String, condition: () -> Boolean) {
        repeat(200) { if (condition()) return; Thread.sleep(100); compose.waitForIdle() }
        throw AssertionError("timed out waiting for $what")
    }
    private fun backend(): FakeBackend {
        var found: FakeBackend? = null
        scenario!!.onActivity { found = ViewModelProvider(it)[AppModel::class.java].fixtureBackend }
        return found!!
    }
    private fun openMovements(plan: String) {
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan)
        scenario = ActivityScenario.launch(intent)
        val tab = tx("Movimientos", "Transactions")
        waitUntil("tab") { compose.onAllNodes(hasText(tab) and isSelectable()).fetchSemanticsNodes().isNotEmpty() }
        compose.onAllNodes(hasText(tab) and isSelectable()).onFirst().performSemanticsAction(SemanticsActions.OnClick)
        // The screen's search field is always on screen; list rows outside it are not composed
        // (LazyColumn), so a seeded row further down cannot stand for "the list is open".
        waitUntil("the movements") { present(tx("Buscar movimientos", "Search transactions")) }
    }
    /** To the background long enough for the process lifecycle to notice, then back. */
    private fun leaveAndReturn() {
        scenario!!.moveToState(Lifecycle.State.CREATED)
        Thread.sleep(1_500)
        scenario!!.moveToState(Lifecycle.State.RESUMED)
    }
    private fun syncCalls() = backend().requests.count { it.method == "POST" && it.url.substringBefore("?").endsWith("/vip/gmail/sync") }

    @Test fun aPurchaseThatArrivedWhileAwayAppearsWhenTheAppComesBack() {
        openMovements("vip")
        Thread.sleep(1_500)  // the launch sync has run; nothing new yet
        backend().mailArrives = true
        assertFalse("not there before the notice arrives", present(FAKE_ARRIVED_MOVEMENT))
        leaveAndReturn()
        waitUntil("the purchase on return, without a pull to refresh") { present(FAKE_ARRIVED_MOVEMENT) }
        assertTrue(syncCalls() >= 2)
    }

    @Test fun freeHasNoMailAndNeverCallsTheSync() {
        openMovements("free")
        leaveAndReturn()
        Thread.sleep(1_500)
        assertTrue("no mailbox read for a plan without mail", syncCalls() == 0)
    }
}
