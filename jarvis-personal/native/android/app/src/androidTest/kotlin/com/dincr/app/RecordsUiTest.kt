package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasScrollToNodeAction
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isRoot
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.printToLog
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * JARVIS → Registros (Owner) on the FakeBackend: the timeline (balance today, the dated events and
 * the balance they leave) and the reconciliation (an account to review, confirming its real
 * balance). Other roles never reach JARVIS (`JarvisAccessUiTest`). iOS: `RecordsUITests`.
 */
class RecordsUiTest {
    @get:Rule val compose = createEmptyComposeRule()

    private var scenario: ActivityScenario<MainActivity>? = null

    @After fun close() { scenario?.close() }

    private fun launchOwner() {
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L)
            .putExtra("dincrPlan", "free").putExtra("dincrRole", "owner")
        scenario = ActivityScenario.launch(intent)
    }

    private fun present(text: String, substring: Boolean = false) =
        compose.onAllNodes(hasText(text, substring = substring), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()

    private fun tagged(tag: String) = compose.onAllNodes(hasTestTag(tag), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()

    private fun waitUntil(what: String, condition: () -> Boolean) {
        try {
            compose.waitUntil(15_000) { compose.mainClock.advanceTimeBy(100); condition() }
        } catch (error: Throwable) {
            runCatching { compose.onAllNodes(isRoot()).printToLog("DINCR-UI") }
            val texts = runCatching {
                compose.onAllNodes(hasText("", substring = true), useUnmergedTree = true).fetchSemanticsNodes().flatMap { node ->
                    (if (node.config.contains(SemanticsProperties.Text)) node.config[SemanticsProperties.Text] else emptyList()).map { it.text }
                }.distinct()
            }.getOrDefault(emptyList())
            throw AssertionError("timed out waiting for $what; screen: $texts", error)
        }
    }

    private fun scrollTo(matcher: androidx.compose.ui.test.SemanticsMatcher) {
        compose.onAllNodes(hasScrollToNodeAction()).fetchSemanticsNodes().indices.forEach { index ->
            runCatching { compose.onAllNodes(hasScrollToNodeAction())[index].performScrollToNode(matcher) }
        }
    }

    private fun waitForText(text: String, substring: Boolean = false) =
        waitUntil("\"$text\"") { present(text, substring) || run { scrollTo(hasText(text, substring = substring)); present(text, substring) } }

    private fun waitForTag(tag: String) = waitUntil("tag $tag") { tagged(tag) || run { scrollTo(hasTestTag(tag)); tagged(tag) } }

    private fun click(text: String) {
        waitForText(text)
        val clickable = compose.onAllNodes(hasText(text) and hasClickAction())
        val node = if (clickable.fetchSemanticsNodes().isNotEmpty()) clickable.onFirst() else compose.onAllNodesWithText(text).onFirst()
        runCatching { node.performScrollTo() }
        node.performClick()
    }

    private fun tapTag(tag: String) {
        waitForTag(tag)
        compose.onNodeWithTag(tag).also { runCatching { it.performScrollTo() } }.performSemanticsAction(SemanticsActions.OnClick)
    }

    private fun openRecords() {
        waitUntil("home") { present(tx("Hoy", "Today")) }
        compose.onAllNodesWithText(tx("Perfil", "Profile")).onFirst().performClick()
        click("JARVIS")
        click(tx("Registros", "Records"))
    }

    @Test fun theTimelineShowsTheBalanceAndTheDatedEvents() {
        launchOwner()
        openRecords()
        waitForTag("records.timeline.summary")
        assertTrue("no longer a placeholder", !present(tx("En restauración", "Being restored")))
        waitForText(tx("Disponible hoy", "Available today"))
        waitForText("Cuota · Préstamo de ejemplo")
        waitForText("Ingreso de salario")
        waitForText(tx("Queda:", "Left:"), substring = true)
    }

    @Test fun confirmingTheRealBalanceSettlesTheAccount() {
        launchOwner()
        openRecords()
        click(tx("Conciliación", "Reconciliation"))
        waitForTag("records.reconciliation.summary")
        waitForText(tx("1 cuenta para revisar", "1 account to review"))
        tapTag("records.confirm.801")
        waitUntil("the amount field") { compose.onAllNodes(hasSetTextAction()).fetchSemanticsNodes().isNotEmpty() }
        compose.onAllNodes(hasSetTextAction()).onFirst().performTextInput("310000")
        click(tx("Confirmar", "Confirm"))
        waitForText(tx("Todas tus cuentas cuadran.", "All your accounts match."))
    }
}
