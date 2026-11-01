package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isSelectable
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performSemanticsAction
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * FA-1 — Movimientos → Análisis → Análisis financiero for VIP and the Owner: their own months in plain
 * words (a normal month, how much is saved and goes to debts, the months side by side, what is above
 * normal this month). Free and Basic see the row locked; it opens Suscripción. JARVIS → Análisis
 * financiero keeps the Owner's full historical analysis. iOS twin: `OwnerAnalysisPlacementUITests`.
 * FakeBackend only.
 */
class OwnerAnalysisPlacementUiTest {
    @get:Rule val compose = createEmptyComposeRule()
    private var scenario: ActivityScenario<MainActivity>? = null

    private fun launch(plan: String = "free", role: String? = null) {
        scenario?.close()
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan)
        role?.let { intent.putExtra("dincrRole", it) }
        scenario = ActivityScenario.launch(intent)
    }

    @After fun close() { scenario?.close() }

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
    private fun click(text: String) {
        waitUntil("\"$text\"") { present(text) }
        val node = compose.onAllNodes(hasText(text) and hasClickAction()).onFirst()
        runCatching { node.performScrollTo() }
        node.performSemanticsAction(SemanticsActions.OnClick)
    }
    private fun openAnalysis() {
        tab(tx("Movimientos", "Transactions"))
        waitUntil("Movimientos") { tagged("movements.analysis") }
        val node = compose.onAllNodes(hasTestTag("movements.analysis") and hasClickAction()).onFirst()
        node.performSemanticsAction(SemanticsActions.OnClick)
        waitUntil("Análisis") { present(tx("Resumen del mes", "Monthly summary")) }
    }

    private val financialAnalysis get() = tx("Análisis financiero", "Financial analysis")
    private fun reveal(tag: String) {
        waitUntil(tag) { tagged(tag) }
        compose.onAllNodes(hasTestTag(tag)).onFirst().performScrollTo()
    }

    @Test fun freeAndBasicSeeTheAnalysisLockedAndItOpensSuscripcion() {
        for (plan in listOf("free", "basic")) {
            launch(plan)
            openAnalysis()
            waitUntil("$plan: locked row") { present(tx("Disponible desde VIP", "Available from VIP")) }
            assertTrue(plan, tagged("analysis.financial"))
            click(financialAnalysis)
            waitUntil("$plan: Suscripción") { present(tx("Suscripción actual", "Current subscription")) }
        }
    }

    @Test fun vipAndTheOwnerReadTheirNumbersInPlainWords() {
        for (role in listOf(null, "owner")) {
            val who = role ?: "vip"
            launch("vip", role = role)
            openAnalysis()
            click(financialAnalysis)
            waitUntil("$who: normal month") { tagged("analysis.financial.left") && present(tx("En un mes normal te sobran", "In a normal month you have")) }
            assertTrue(who, present(tx("Guardás 10 de cada 100 que entran.", "You save 10 of every 100 that come in.")))
            // HS-1: the simple health reading on top (one word, a reason, one action).
            assertTrue(who, tagged("analysis.financial.health") && present(tx("Tu salud financiera", "Your financial health")))
            assertTrue(who, tagged("analysis.financial.debts"))
            reveal("analysis.financial.months")
            reveal("analysis.financial.rises")
            assertTrue(who, present(tx("Comida:", "Comida:")))
            // Not the Owner's historical analysis: no score and no net worth here.
            assertFalse(who, tagged("jarvis.analysis.flow") || tagged("analysis.networth") || present(tx("Salud financiera", "Financial health")))
        }
    }

    @Test fun jarvisKeepsTheFullAnalysis() {
        launch("vip", role = "owner")
        tab(tx("Perfil", "Profile"))
        click("JARVIS")
        click(financialAnalysis)
        waitUntil("net worth") { tagged("analysis.networth") }
        waitUntil("health") { present(tx("Salud financiera", "Financial health")) }
    }
}
