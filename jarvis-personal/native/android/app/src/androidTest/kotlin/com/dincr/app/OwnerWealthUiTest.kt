package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.SemanticsMatcher
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
 * JARVIS → Patrimonio (Owner) on the FakeBackend: the investments (the invented portfolio, its
 * positions, "Actualizar desde IBKR") and the businesses (creating one and recording a movement on
 * it). Other roles never reach JARVIS (`JarvisAccessUiTest`). iOS: `OwnerWealthUITests`.
 */
class OwnerWealthUiTest {
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
    private fun scrollTo(matcher: SemanticsMatcher) {
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

    private fun openWealth() {
        waitUntil("home") { present(tx("Hoy", "Today")) }
        compose.onAllNodesWithText(tx("Perfil", "Profile")).onFirst().performClick()
        click("JARVIS")
        click(tx("Patrimonio, inversiones y negocios", "Net worth, investments and businesses"))
        waitForTag("wealth.investments")
    }

    @Test fun theOwnerSeesThePortfolioAndItsPositions() {
        launchOwner()
        openWealth()
        assertTrue("no longer a placeholder", !present(tx("Esta función todavía no está disponible en la app.", "This feature isn’t available in the app yet."), substring = true))
        waitForText(tx("Valor de mercado", "Market value"))
        waitForText(tx("Rendimiento", "Return"))
        waitForText(tx("Actualizado hace 5 h", "Updated 5 h ago"))
        assertTrue("a known portfolio is not 'no data'", !present(tx("Todavía no hay datos de tu portafolio", "There’s no portfolio data yet")))
        waitForText("ETF de ejemplo")
        waitForText("Acción de ejemplo")
        tapTag("wealth.sync")
        waitForText(tx("Actualizado hace menos de 1 h", "Updated less than 1 h ago"))
        waitForTag("wealth.netWorth")
    }

    @Test fun theOwnerCreatesABusinessAndRecordsAMovement() {
        launchOwner()
        openWealth()
        click(tx("Negocios", "Businesses"))
        waitForTag("wealth.businesses")
        waitForText("Negocio de ejemplo")
        waitForTag("wealth.business.9101")

        tapTag("wealth.addBusiness")
        waitForTag("wealth.business.name")
        compose.onNodeWithTag("wealth.business.name").performTextInput("Negocio nuevo de ejemplo")
        tapTag("wealth.business.save")
        waitForText("Negocio nuevo de ejemplo")

        val newBusiness = SemanticsMatcher("the new business's Registrar movimiento") { node ->
            node.config.getOrNull(SemanticsProperties.TestTag)?.let { it.startsWith("wealth.addMovement.") && it != "wealth.addMovement.9101" } == true
        }
        waitUntil("the new business's button") {
            compose.onAllNodes(newBusiness).fetchSemanticsNodes().isNotEmpty() || run { scrollTo(newBusiness); compose.onAllNodes(newBusiness).fetchSemanticsNodes().isNotEmpty() }
        }
        compose.onAllNodes(newBusiness).onFirst().also { runCatching { it.performScrollTo() } }.performSemanticsAction(SemanticsActions.OnClick)
        waitForTag("wealth.movement.ledgerNote")
        compose.onNodeWithTag("wealth.movement.amount").performTextInput("25000")
        compose.onNodeWithTag("wealth.movement.description").performTextInput("Primera venta de ejemplo")
        tapTag("wealth.movement.save")
        waitForText("Primera venta de ejemplo")
    }
}
