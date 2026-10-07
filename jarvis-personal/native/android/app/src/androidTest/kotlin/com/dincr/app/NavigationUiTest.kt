package com.dincr.app

import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.isSelectable
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import android.content.Intent
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * UX-13 — the public navigation is exactly Hoy · Movimientos · Plan · Patrimonio · Perfil, and every
 * function of the retired DINCR tab is reached from its new home: Movimientos → Análisis (summary,
 * reports, monthly review), Patrimonio (projections, scenarios) and Hoy → Para atender (DINCR hoy).
 * iOS twin: `NavigationUITests`. FakeBackend only. Copy is resolved with the app's own `tx`.
 */
class NavigationUiTest {
    @get:Rule val compose = createEmptyComposeRule()
    private var scenario: ActivityScenario<MainActivity>? = null
    private val tabs get() = listOf(tx("Hoy", "Today"), tx("Movimientos", "Transactions"), tx("Plan", "Plan"), tx("Patrimonio", "Wealth"), tx("Perfil", "Profile"))

    private fun launch(plan: String = "free", role: String? = null) {
        scenario?.close()
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan)
        role?.let { intent.putExtra("dincrRole", it) }
        scenario = ActivityScenario.launch(intent)
    }

    @After fun close() { scenario?.close() }

    private fun present(text: String) = compose.onAllNodes(hasText(text), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    private fun tagged(tag: String) = compose.onAllNodes(hasTestTag(tag), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    private fun waitUntil(what: String, condition: () -> Boolean) {
        repeat(150) { if (condition()) return; Thread.sleep(100); compose.waitForIdle() }
        throw AssertionError("timed out waiting for $what")
    }
    private fun click(text: String) {
        waitUntil("\"$text\"") { present(text) }
        val clickable = compose.onAllNodes(hasText(text) and hasClickAction())
        val node = if (clickable.fetchSemanticsNodes().isNotEmpty()) clickable.onFirst() else compose.onAllNodesWithText(text).onFirst()
        runCatching { node.performScrollTo() }
        node.performSemanticsAction(SemanticsActions.OnClick)
    }
    private fun tab(text: String) = compose.onAllNodes(hasText(text) and isSelectable()).onFirst().performSemanticsAction(SemanticsActions.OnClick)
    private fun back() { scenario?.onActivity { it.onBackPressedDispatcher.onBackPressed() }; compose.waitForIdle() }
    private fun tabLabels(): List<String> = compose.onAllNodes(isSelectable(), useUnmergedTree = false).fetchSemanticsNodes()
        .mapNotNull { node -> node.config.getOrNull(androidx.compose.ui.semantics.SemanticsProperties.Text)?.joinToString("") { it.text } }
        .filter { it in tabs || it == "DINCR" }

    @Test fun everyPlanHasExactlyTheFiveFinalTabs() {
        listOf("free", "basic", "vip").forEach { plan ->
            launch(plan)
            waitUntil("Hoy for $plan") { present(tx("Hoy", "Today")) }
            assertEquals(plan, tabs, tabLabels())
            assertTrue("$plan: no DINCR tab", !present("DINCR"))
        }
    }

    @Test fun vipReachesEveryFormerDincrFunctionInItsNewHome() {
        launch("vip")
        waitUntil("Hoy") { present(tx("Hoy", "Today")) }
        // DINCR hoy: the proactive advisor's changes are in Hoy → Para atender (and "Ver todas").
        waitUntil("Para atender") { tagged("home.attention") }
        tab(tx("Movimientos", "Transactions"))
        click(tx("Análisis", "Analysis"))
        click(tx("Resumen del mes", "Monthly summary")); waitUntil("summary") { present(tx("Ingresos", "Income")) }; back()
        click(tx("Reportes", "Reports")); waitUntil("reports") { present(tx("Pagos de deuda", "Debt payments")) }; back()
        click(tx("Revisión del mes", "Monthly review")); waitUntil("review") { present(tx("Revisión mensual", "Monthly review")) }; back()
        back()
        tab(tx("Patrimonio", "Wealth"))
        click(tx("Proyecciones", "Projections")); waitUntil("projections") { present(tx("Proyecciones", "Projections")) }; back()
        click(tx("Escenarios", "Scenarios")); waitUntil("scenarios") { present(tx("Escenarios", "Scenarios")) }; back()
    }

    @Test fun theGatesStayPerPlan() {
        launch("free")
        waitUntil("Hoy") { present(tx("Hoy", "Today")) }
        tab(tx("Movimientos", "Transactions"))
        click(tx("Análisis", "Analysis"))
        waitUntil("summary row") { present(tx("Resumen del mes", "Monthly summary")) }
        waitUntil("locked from Basic") { present(tx("Disponible desde Basic", "Available from Basic")) }
        waitUntil("locked from VIP") { present(tx("Disponible desde VIP", "Available from VIP")) }
        back()
        tab(tx("Patrimonio", "Wealth"))
        waitUntil("projections locked") { present(tx("Proyecciones", "Projections")) && present(tx("Disponible desde VIP", "Available from VIP")) }
        launch("basic")
        waitUntil("Hoy") { present(tx("Hoy", "Today")) }
        tab(tx("Movimientos", "Transactions"))
        click(tx("Análisis", "Analysis"))
        waitUntil("reports open for Basic") { present(tx("Tu mes comparado con el anterior", "Your month vs the previous one")) }
        assertTrue("Basic: no Basic lock", !present(tx("Disponible desde Basic", "Available from Basic")))
        waitUntil("review locked for Basic") { present(tx("Disponible desde VIP", "Available from VIP")) }
    }

    @Test fun theOwnerKeepsTheFiveTabsAndJarvis() {
        launch("vip", role = "owner")
        waitUntil("Hoy") { present(tx("Hoy", "Today")) }
        assertEquals(tabs, tabLabels())
        tab(tx("Perfil", "Profile"))
        click("JARVIS")
        waitUntil("JARVIS") { present(tx("Tu espacio personal", "Your personal space")) || present("Chat") }
    }
}
