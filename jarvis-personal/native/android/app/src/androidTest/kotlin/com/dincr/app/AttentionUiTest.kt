package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.hasScrollToNodeAction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performSemanticsAction
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * "Para atender" (UX-5) on the FakeBackend: VIP's populated command center has four matters (a high
 * one, two medium alerts and the pending mail notices, which the backend also raises as an alert),
 * so Hoy shows three and "Ver todas". Free and Basic have no section; the Owner's Hoy shares it.
 * Synthetic data only. The Swift twin is `AttentionUITests`.
 */
class AttentionUiTest {
    @get:Rule val compose = createEmptyComposeRule()

    private var scenario: ActivityScenario<MainActivity>? = null

    @After fun close() { scenario?.close() }

    private fun launch(plan: String, role: String? = null) {
        scenario?.close()
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan)
        role?.let { intent.putExtra("dincrRole", it) }
        scenario = ActivityScenario.launch(intent)
    }

    private fun tags(tag: String) = compose.onAllNodes(hasTestTag(tag), useUnmergedTree = true).fetchSemanticsNodes()
    private fun texts(text: String) = compose.onAllNodes(hasText(text, substring = true), useUnmergedTree = true).fetchSemanticsNodes()

    private fun waitFor(what: String, condition: () -> Boolean) = compose.waitUntil(15_000) {
        compose.mainClock.advanceTimeBy(100)
        condition() || run {
            compose.onAllNodes(hasScrollToNodeAction()).fetchSemanticsNodes().indices.forEach { index ->
                runCatching { compose.onAllNodes(hasScrollToNodeAction())[index].performScrollToNode(hasTestTag(what)) }
                runCatching { compose.onAllNodes(hasScrollToNodeAction())[index].performScrollToNode(hasText(what, substring = true)) }
            }
            condition()
        }
    }

    private fun waitForTag(tag: String) = waitFor(tag) { tags(tag).isNotEmpty() }
    private fun waitForText(text: String) = waitFor(text) { texts(text).isNotEmpty() }
    private fun clickTag(tag: String) {
        waitForTag(tag)
        compose.onAllNodes(hasTestTag(tag)).onFirst().performSemanticsAction(SemanticsActions.OnClick)
    }

    private fun top(text: String) = texts(text).first().boundsInRoot.top

    @Test fun vipHoyShowsThreeMattersInOrderAndSeeAll() {
        launch("vip")
        waitForTag("home.attention")
        waitForTag("home.attention.all")
        waitForText("Reserva menor a un mes")
        assertTrue("high before medium", top("Reserva menor a un mes") < top("Pago de tarjeta en 5 días"))
        assertTrue(texts("Recurrente con variación").isNotEmpty())
        // The fourth (the mail notices, last among the medium ones) waits behind "Ver todas".
        assertTrue(texts("Movimientos por revisar").isEmpty())
        // A command-center action is free text: shown as words, never a link.
        assertTrue(texts("Revisá la deuda").isNotEmpty())
        assertTrue(tags("home.attention.link.debts").isEmpty())
        assertTrue(tags("home.attention.link.review").isEmpty())
    }

    @Test fun seeAllListsEveryMatterOnceAndOpensTheMailReview() {
        launch("vip")
        clickTag("home.attention.all")
        waitForTag("attention.list")
        waitForTag("attention.link.review")
        // The backend's pending-review alert and the mail count are one item: four matters in all.
        assertEquals(1, tags("attention.item.review").size)
        assertEquals(3, tags("attention.item.center").size)
        // The advisor answered (no earlier observation yet): no technical problem, no invented change.
        assertTrue(tags("attention.advisor.unavailable").isEmpty())
        assertTrue(tags("attention.item.advisor").isEmpty())
        assertTrue(tags("attention.none").isEmpty())
        clickTag("attention.link.review")
        waitForText(tx("Por revisar", "To review"))
    }

    @Test fun freeAndBasicHaveNoAttentionSection() {
        for (plan in listOf("free", "basic")) {
            launch(plan)
            waitForText(tx("Hoy", "Today"))
            waitForText(tx("Deudas", "Debts"))
            assertFalse(plan, tags("home.attention").isNotEmpty())
            assertFalse(plan, texts(tx("Nada pendiente", "Nothing pending")).isNotEmpty())
        }
    }

    @Test fun theOwnersHoySharesTheSection() {
        launch("free", role = "owner")
        waitForTag("home.attention.all")
        waitForText("Reserva menor a un mes")
        assertTrue("high before medium", top("Reserva menor a un mes") < top("Pago de tarjeta en 5 días"))
    }
}
