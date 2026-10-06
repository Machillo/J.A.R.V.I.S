package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.hasClickAction
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
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * Hoy (UX-6) on the FakeBackend: four blocks for every public plan — Estado de hoy, Para atender
 * (VIP only: Free and Basic have no source), Qué sigue (one thing), Accesos rápidos (the same four) —
 * and the Owner's JARVIS space before them. Synthetic data only. The Swift twin is `HomeTodayUITests`.
 */
class HomeTodayUiTest {
    @get:Rule val compose = createEmptyComposeRule()

    private var scenario: ActivityScenario<MainActivity>? = null

    @After fun close() { scenario?.close() }

    private fun launch(plan: String, role: String? = null, fixture: String = "POPULATED") {
        scenario?.close()
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", fixture).putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan)
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

    /** What no public Hoy shows as a main block any more. */
    private fun assertNoRetiredBlocks(plan: String) {
        for (retired in listOf("Salud financiera", "/100", "Tu hoja de ruta", "Tu plan de acción", "Patrimonio neto", "En 6 meses",
            "Ingresos y gastos", "En qué se va el dinero")) {
            assertTrue("$plan: $retired", texts(retired).isEmpty())
        }
    }

    private fun assertQuickAccess() {
        for (tag in listOf("home.shortcut.registerMovement", "home.shortcut.movements", "home.debts", "home.goals")) waitForTag(tag)
    }

    @Test fun freeShowsRealFactsAndNoIntelligence() {
        launch("free")
        waitForTag("home.status")
        waitForText(tx("Resultado del mes", "This month’s result"))
        waitForTag("home.status.amount")
        assertTrue(texts(tx("Podés gastar con tranquilidad", "Safe to spend")).isEmpty())
        assertTrue("Free has no source for Para atender", tags("home.attention").isEmpty())
        assertTrue(tags("home.status.budget").isEmpty())
        waitForTag("home.next")
        assertQuickAccess()
        assertNoRetiredBlocks("free")
    }

    @Test fun freeWithoutIncomeSaysWhatIsMissingAndOpensTheRealIncomeFlow() {
        launch("free", fixture = "EMPTY")
        waitForTag("home.status.unknown")
        assertTrue("unknown, never ₡0", tags("home.status.amount").isEmpty())
        clickTag("home.status.help")
        clickTag("home.status.missing.income")
        // The existing movement editor, opened as an income (salary / pay stub categories).
        waitForText("Salario")
    }

    @Test fun basicAddsItsBudgetWithoutVipIntelligence() {
        launch("basic")
        waitForTag("home.status")
        waitForTag("home.status.budget")
        waitForTag("home.status.pending")
        assertTrue(texts(tx("Podés gastar con tranquilidad", "Safe to spend")).isEmpty())
        assertTrue(tags("home.attention").isEmpty())
        waitForTag("home.next")
        assertQuickAccess()
        assertNoRetiredBlocks("basic")
    }

    @Test fun vipShowsSafeToSpendOneRecommendationAndAttention() {
        launch("vip")
        waitForTag("home.status.amount")
        waitForText(tx("Podés gastar con tranquilidad", "Safe to spend"))
        waitForTag("home.attention")
        waitForTag("home.next")
        waitForText("Tu prioridad es bajar la tarjeta")
        assertQuickAccess()
        assertNoRetiredBlocks("vip")
        clickTag("home.next.action")
        waitForText(tx("Sobrante para repartir", "Surplus to allocate"))  // Plan → Tu plan del mes
    }

    @Test fun ownerHasJarvisFirstThenTheFinancialBlocks() {
        launch("free", role = "owner")
        waitForTag("owner.home.greeting")
        waitForTag("owner.home.jarvis.chat")
        waitForTag("home.status")
        val jarvis = tags("owner.home.jarvis.chat").first().positionInRoot.y
        val status = tags("home.status").first().positionInRoot.y
        assertTrue("JARVIS comes first", jarvis < status)
        waitForTag("owner.home.jarvis.agenda")
        waitForTag("owner.home.jarvis.hub")
        waitForTag("owner.home")
        assertFalse("the Owner never gets the public Hoy", tags("home.today").isNotEmpty())
        assertQuickAccess()
        // The JARVIS row inside the tagged container is what takes the tap.
        compose.onAllNodes(hasAnyAncestor(hasTestTag("owner.home.jarvis.chat")) and hasClickAction()).onFirst()
            .performSemanticsAction(SemanticsActions.OnClick)
        waitForTag("jarvis.chat.input")
    }

    @Test fun otherAccountsNeverSeeTheOwnersJarvisSpace() {
        for (plan in listOf("free", "basic", "vip")) {
            launch(plan)
            waitForTag("home.status")
            assertTrue(plan, tags("owner.home.greeting").isEmpty() && tags("owner.home.jarvis.chat").isEmpty() && tags("owner.home").isEmpty())
        }
    }
}
