package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasScrollToNodeAction
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
 * JARVIS → Control de dinero (Owner) on the FakeBackend: who owes the Owner money (two invented
 * people), their history, recording a payment and a new collection. Other roles never reach JARVIS
 * (`JarvisAccessUiTest`). iOS: `MoneyControlUITests`.
 */
class MoneyControlUiTest {
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

    /** Brings a node into composition and view: small screens (CI emulators) hide it otherwise. */
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

    private fun openMoneyControl() {
        waitUntil("home") { present(tx("Hoy", "Today")) }
        compose.onAllNodesWithText(tx("Perfil", "Profile")).onFirst().performClick()
        click("JARVIS")
        click(tx("Control de dinero", "Money control"))
        waitForTag("money.summary")
    }

    @Test fun theOwnerSeesWhoOwesHimAndTheirHistory() {
        launchOwner()
        openMoneyControl()
        assertTrue("no longer a placeholder", !present(tx("En restauración", "Being restored")))
        waitForText(tx("Te deben", "Owed to you"))
        waitForText(tx("2 personas con saldo pendiente", "2 people with an amount due"))
        waitForText("Ana de ejemplo")
        waitForText("Luis de ejemplo")
        waitForText(tx("Tarjeta adicional", "Additional card"), substring = true)
        tapTag("money.history.7002")
        waitForText("Compra con tarjeta adicional", substring = true)
    }

    @Test fun recordingAPaymentSettlesThePerson() {
        launchOwner()
        openMoneyControl()
        tapTag("money.pay.7001")
        waitUntil("the amount field") { present(tx("Monto", "Amount")) }
        compose.onAllNodes(hasText(tx("Monto", "Amount")) and androidx.compose.ui.test.hasSetTextAction()).onFirst().performTextInput("35000")
        click(tx("Registrar", "Record"))
        waitForText(tx("Al día", "Settled"), substring = true)
        assertTrue("a settled person has nothing to pay", !tagged("money.pay.7001"))
    }

    @Test fun aNewCollectionAddsThePerson() {
        launchOwner()
        openMoneyControl()
        tapTag("money.add")
        waitForTag("money.entry.person")
        compose.onNodeWithTag("money.entry.person").performTextInput("Marta de ejemplo")
        compose.onNodeWithTag("money.entry.amount").performTextInput("12000")
        tapTag("money.entry.save")
        waitForText("Marta de ejemplo")
        waitForText(tx("3 personas con saldo pendiente", "3 people with an amount due"))
    }
}
