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
 * §15 PR 11 — the Owner's historical financial analysis in Movimientos → Análisis, in its Análisis
 * mode: income and expenses, spending by category, month end and recommendations, with no health score
 * (P3.7) and no net worth (P0.9). Free, Basic and VIP never see the entry. JARVIS → Análisis financiero
 * keeps every section. iOS twin: `OwnerAnalysisPlacementUITests`. FakeBackend only.
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

    @Test fun freeBasicAndVipNeverSeeTheOwnerEntry() {
        for (plan in listOf("free", "basic", "vip")) {
            launch(plan)
            openAnalysis()
            assertFalse(plan, tagged("analysis.owner") || present(financialAnalysis))
        }
    }

    @Test fun theOwnerSeesTheAnalysisModeWithoutScoreOrNetWorth() {
        launch("vip", role = "owner")
        openAnalysis()
        click(financialAnalysis)
        waitUntil("flow") { tagged("jarvis.analysis.flow") }
        waitUntil("month end") { tagged("jarvis.analysis.monthEnd") && present(tx("Saldo proyectado al cierre", "Projected month-end balance")) }
        assertTrue(tagged("jarvis.analysis.spending"))
        assertFalse("no net worth", tagged("analysis.networth") || present(tx("Patrimonio neto", "Net worth")))
        assertFalse("no health score", present(tx("Salud financiera", "Financial health")) || present("/ 100") || present("de 100"))
        // Opened from Movimientos, the Owner's analysis stays in Movimientos.
        assertTrue(compose.onAllNodes(hasText(tx("Movimientos", "Transactions")) and isSelectable()).fetchSemanticsNodes().isNotEmpty())
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
