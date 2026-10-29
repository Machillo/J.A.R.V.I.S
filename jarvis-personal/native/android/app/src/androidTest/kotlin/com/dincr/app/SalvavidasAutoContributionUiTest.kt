package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasScrollToNodeAction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.performTextInput
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * Salvavidas → Aportes automáticos on the FakeBackend (Debug only; synthetic data): a VIP ticks the
 * box, fills the plan, saves once and sees the breakdown under the balance; unknown savings ask for
 * today's balance; the annual interest rate is the Owner's alone. iOS: `SalvavidasAutoContributionUITests`.
 */
class SalvavidasAutoContributionUiTest {
    @get:Rule val compose = createEmptyComposeRule()

    private var scenario: ActivityScenario<MainActivity>? = null

    @After fun close() { scenario?.close() }

    private fun launch(plan: String = "vip", role: String? = null, fixture: String = "POPULATED") {
        scenario?.close()
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", fixture).putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan)
        role?.let { intent.putExtra("dincrRole", it) }
        scenario = ActivityScenario.launch(intent)
    }

    private fun advance() { compose.mainClock.advanceTimeBy(100) }

    private fun present(text: String) = compose.onAllNodes(hasText(text), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    private fun tagPresent(tag: String) = compose.onAllNodes(hasTestTag(tag), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()

    private fun scrollTo(matcher: androidx.compose.ui.test.SemanticsMatcher) {
        compose.onAllNodes(hasScrollToNodeAction()).fetchSemanticsNodes().indices.forEach { index ->
            runCatching { compose.onAllNodes(hasScrollToNodeAction())[index].performScrollToNode(matcher) }
        }
    }

    private fun waitForText(text: String) = compose.waitUntil(15_000) { advance(); present(text) || run { scrollTo(hasText(text)); present(text) } }
    private fun waitForTag(tag: String) = compose.waitUntil(15_000) { advance(); tagPresent(tag) || run { scrollTo(hasTestTag(tag)); tagPresent(tag) } }

    private fun click(text: String) {
        waitForText(text)
        val clickable = compose.onAllNodes(hasText(text) and hasClickAction())
        if (clickable.fetchSemanticsNodes().isNotEmpty()) {
            clickable.onFirst().also { runCatching { it.performScrollTo() } }.performSemanticsAction(SemanticsActions.OnClick)
            return
        }
        compose.onAllNodesWithText(text).onFirst().also { runCatching { it.performScrollTo() } }.performClick()
    }

    private fun tapTag(tag: String) {
        waitForTag(tag)
        compose.onNodeWithTag(tag).also { runCatching { it.performScrollTo() } }.performSemanticsAction(SemanticsActions.OnClick)
    }

    private fun type(tag: String, text: String) {
        waitForTag(tag)
        compose.onNodeWithTag(tag).also { runCatching { it.performScrollTo() } }.performTextInput(text)
    }

    private fun openSalvavidas() {
        waitForText(tx("Hoy", "Today"))
        click(tx("Plan", "Plan"))
        click(tx("Salvavidas", "Emergency fund"))
        waitForTag("salvavidas.fund")
    }

    @Test fun aVipTicksTheBoxSavesThePlanAndSeesTheBreakdown() {
        // The store account has declared savings, so no balance is asked for.
        launch(fixture = "STORE")
        openSalvavidas()
        assertTrue("no breakdown before a plan", !tagPresent("salvavidas.breakdown"))
        waitForTag("salvavidas.auto.enabled")
        assertTrue("the fields wait for the box", !tagPresent("salvavidas.auto.amount"))
        tapTag("salvavidas.auto.enabled")
        type("salvavidas.auto.amount", "10000")
        assertTrue("known savings are not asked again", !tagPresent("salvavidas.auto.current"))
        assertTrue("the interest rate is never offered to a VIP", !tagPresent("salvavidas.auto.rate"))
        tapTag("salvavidas.auto.save")
        waitForTag("salvavidas.breakdown")
        waitForTag("salvavidas.breakdown.next")
        waitForText(tx("Según tu plan de aportes; actualizá el saldo real cuando quieras.", "Following your contribution plan; update the real balance whenever you like."))
        assertTrue("no interest for a VIP", !tagPresent("salvavidas.breakdown.interest"))
    }

    @Test fun unknownSavingsAskForTodaysBalance() {
        launch()
        openSalvavidas()
        tapTag("salvavidas.auto.enabled")
        waitForTag("salvavidas.auto.current")
        assertTrue(!tagPresent("salvavidas.auto.rate"))
    }

    @Test fun theOwnerHasTheInterestRate() {
        launch(plan = "free", role = "owner")
        openSalvavidas()
        waitForTag("salvavidas.auto.rate")
        tapTag("salvavidas.auto.enabled")
        type("salvavidas.auto.amount", "10000")
        type("salvavidas.auto.rate", "2,5")
        tapTag("salvavidas.auto.save")
        waitForTag("salvavidas.breakdown.interest")
    }
}
