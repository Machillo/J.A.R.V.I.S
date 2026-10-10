package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isSelectable
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.performTouchInput
import androidx.compose.ui.test.swipeDown
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * NAT-03 (B17 finding): a pull to refresh that fails on Hoy or Movimientos keeps what the screen
 * shows and says so in the app notice, instead of replacing it with an error. NAT-02: a temporary
 * failure when the app returns to the foreground keeps the user where they were (as iOS), instead of
 * the account-error screen. iOS twin: `KeepContentUITests`. FakeBackend only: `dincrRefreshFails`
 * makes the identity read again fail, and the test makes Hoy's main source and the movement list
 * unreachable right before pulling (Android re-reads Hoy at start, so a read count can't stand for
 * "a pull").
 */
class KeepContentUiTest {
    @get:Rule val compose = createEmptyComposeRule()
    private var scenario: ActivityScenario<MainActivity>? = null

    private fun launch() {
        scenario?.close()
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L)
            .putExtra("dincrPlan", "free").putExtra("dincrRefreshFails", true)
        scenario = ActivityScenario.launch(intent)
        waitUntil("Hoy") { tagged("home.today") }
    }

    @After fun close() { scenario?.close() }

    private val failureNotice get() = tx("No pudimos actualizar. Seguís viendo la información anterior.", "We couldn’t refresh. You’re still seeing the previous information.")
    private val retry get() = tx("Reintentar", "Try again")

    private fun present(text: String) = compose.onAllNodes(hasText(text, substring = true), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    private fun tagged(tag: String) = compose.onAllNodes(hasTestTag(tag), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    private fun waitUntil(what: String, condition: () -> Boolean) {
        repeat(150) { if (condition()) return; Thread.sleep(100); compose.waitForIdle() }
        throw AssertionError("timed out waiting for $what")
    }
    private fun tab(text: String) {
        waitUntil("tab $text") { compose.onAllNodes(hasText(text) and isSelectable()).fetchSemanticsNodes().isNotEmpty() }
        compose.onAllNodes(hasText(text) and isSelectable()).onFirst().performSemanticsAction(SemanticsActions.OnClick)
    }
    private fun serverUnreachable() {
        scenario!!.onActivity { ViewModelProvider(it)[AppModel::class.java].fixtureBackend!!.refreshedSourcesUnreachable = true }
    }

    /** The gesture on the screen's refresh box (as the tabs' `tab.refresh` in PullToRefreshUiTest). */
    private fun pull(tag: String) {
        waitUntil(tag) { tagged(tag) }
        compose.onAllNodes(hasTestTag(tag)).onFirst().performTouchInput { swipeDown() }
        compose.waitForIdle()
    }

    @Test fun aFailedHoyRefreshKeepsHoyAndSaysSo() {
        launch()
        waitUntil("Hoy's blocks") { !present(retry) && present(tx("Accesos rápidos", "Quick access")) }
        serverUnreachable()
        pull("home.refresh")
        waitUntil("the failure notice") { present(failureNotice) }
        assertTrue("Hoy stays", tagged("home.today") && present(tx("Accesos rápidos", "Quick access")))
        assertFalse("no error screen replaces Hoy", present(retry))
    }

    @Test fun aFailedMovementsRefreshKeepsTheList() {
        launch()
        tab(tx("Movimientos", "Transactions"))
        waitUntil("a movement") { present("Supermercado") }
        serverUnreachable()
        pull("movements.refresh")
        waitUntil("the failure notice") { present(failureNotice) }
        assertTrue("the list stays", present("Supermercado"))
        assertFalse("no error screen replaces the list", present(retry))
    }

    @Test fun aTemporaryFailureOnResumeKeepsTheUserWhereTheyWere() {
        launch()
        val before = identityReads()
        // The identity is read again on resume only after its 15-second throttle.
        Thread.sleep(16_000)
        scenario!!.moveToState(Lifecycle.State.CREATED)
        // onForeground follows the process lifecycle, which reports the background ~700 ms after the
        // last activity stops: stay there long enough for the return to count as a resume.
        Thread.sleep(1_500)
        scenario!!.moveToState(Lifecycle.State.RESUMED)
        // A GET that answers 503 is retried twice with backoff (ApiClient): wait for all three attempts,
        // then for the app to act on the final failure.
        waitUntil("the identity read again, with its retries") { identityReads() >= before + 3 }
        Thread.sleep(1_500)
        compose.waitForIdle()
        assertTrue("still in the app (the identity read again failed like an unreachable server)", tagged("home.today"))
        assertFalse("no account-error screen", present(tx("No pudimos cargar tu cuenta", "We couldn’t load your account")) || present("Servicio no disponible"))
    }

    private fun identityReads(): Int {
        var count = 0
        scenario!!.onActivity { activity ->
            count = ViewModelProvider(activity)[AppModel::class.java].fixtureBackend!!.requests.toList()
                .count { it.method == "GET" && it.url.substringBefore("?").endsWith("/auth/me") }
        }
        return count
    }

}
