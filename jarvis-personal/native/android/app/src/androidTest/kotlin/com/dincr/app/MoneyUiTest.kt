package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasScrollToNodeAction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isDialog
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
 * JARVIS → Mi dinero (Owner) on the FakeBackend: the cycle (expected and received income, the
 * period's spending, the real balance) and the accounts (adding one, removing one after confirming).
 * Other roles never reach JARVIS (`JarvisAccessUiTest`). iOS: `MoneyUITests`.
 */
class MoneyUiTest {
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

    private fun openMoney() {
        waitUntil("home") { present(tx("Hoy", "Today")) }
        compose.onAllNodesWithText(tx("Perfil", "Profile")).onFirst().performClick()
        click("JARVIS")
        click(tx("Mi dinero", "My money"))
        waitForTag("money.cycle")
    }

    @Test fun theCycleAndTheAccountsShow() {
        launchOwner()
        openMoney()
        assertTrue("no longer a placeholder", !present(tx("En restauración", "Being restored")))
        waitForText(tx("Ingresos esperados", "Expected income"))
        waitForText(tx("Saldo real", "Real balance"))
        waitForTag("money.accounts")
        waitForText("Cuenta de ejemplo", substring = true)
        waitForText("Ahorro en dólares", substring = true)
        waitForText(tx("No suma a tu patrimonio", "Doesn’t count toward your net worth"))
    }

    @Test fun aNewAccountIsListed() {
        launchOwner()
        openMoney()
        tapTag("money.add")
        waitForTag("money.form.name")
        compose.onNodeWithTag("money.form.name").performTextInput("Cuenta nueva de ejemplo")
        compose.onNodeWithTag("money.form.balance").performTextInput("50000")
        tapTag("money.form.save")
        waitForText("Cuenta nueva de ejemplo", substring = true)
    }

    @Test fun removingAnAccountAsksFirst() {
        launchOwner()
        openMoney()
        waitForText("Detectada por correo", substring = true)
        tapTag("money.delete.903")
        val confirm = hasText(tx("Quitar", "Remove")) and hasClickAction() and hasAnyAncestor(isDialog())
        waitUntil("the confirmation") { compose.onAllNodes(confirm).fetchSemanticsNodes().isNotEmpty() }
        compose.onAllNodes(confirm).onFirst().performClick()
        waitUntil("the account removed") { !present("Detectada por correo", substring = true) }
        waitForText("Cuenta de ejemplo", substring = true)
    }
}
