package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isSelectable
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.hasAnyDescendant
import androidx.compose.ui.test.hasScrollAction
import androidx.compose.ui.test.performScrollToNode
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * UX-14 — Patrimonio → Proyecciones: a VIP with every input known sees the 1, 3, 6 and 12-month
 * points; a VIP with unknown inputs sees no figure, only what is missing and a link to the existing
 * screen that takes it. Hoy shows no projection. iOS twin: `ProjectionsUITests`. FakeBackend only.
 */
class ProjectionsUiTest {
    @get:Rule val compose = createEmptyComposeRule()
    private var scenario: ActivityScenario<MainActivity>? = null

    private fun launch(fixtures: String = "POPULATED", plan: String = "vip") {
        scenario?.close()
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", fixtures).putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan)
        scenario = ActivityScenario.launch(intent)
    }

    @After fun close() { scenario?.close() }

    private fun present(text: String) = compose.onAllNodes(hasText(text, substring = true, ignoreCase = true), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    private fun tagged(tag: String) = compose.onAllNodes(hasTestTag(tag), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    private fun waitUntil(what: String, condition: () -> Boolean) {
        repeat(150) { if (condition()) return; Thread.sleep(100); compose.waitForIdle() }
        throw AssertionError("timed out waiting for $what")
    }
    /** Brings a tagged node into view (it may sit below the fold on a small screen). */
    private fun reveal(tag: String): Boolean {
        val scrollable = compose.onAllNodes(hasScrollAction() and hasAnyDescendant(hasTestTag(tag)))
        if (scrollable.fetchSemanticsNodes().isNotEmpty()) runCatching { scrollable.onFirst().performScrollToNode(hasTestTag(tag)) }
        return tagged(tag)
    }
    private fun clickTag(tag: String) {
        waitUntil(tag) { reveal(tag) }
        val clickable = compose.onAllNodes(hasTestTag(tag) and hasClickAction(), useUnmergedTree = true)
        val node = if (clickable.fetchSemanticsNodes().isNotEmpty()) clickable.onFirst() else compose.onAllNodes(hasTestTag(tag), useUnmergedTree = true).onFirst()
        runCatching { node.performScrollTo() }
        node.performSemanticsAction(SemanticsActions.OnClick)
    }
    private fun click(text: String) {
        waitUntil("\"$text\"") { present(text) }
        val node = compose.onAllNodes(hasText(text) and hasClickAction()).onFirst()
        runCatching { node.performScrollTo() }
        node.performSemanticsAction(SemanticsActions.OnClick)
    }
    private fun tab(text: String) {
        waitUntil("tab $text") { compose.onAllNodes(hasText(text) and isSelectable()).fetchSemanticsNodes().isNotEmpty() }
        compose.onAllNodes(hasText(text) and isSelectable()).onFirst().performSemanticsAction(SemanticsActions.OnClick)
    }
    private fun back() { scenario?.onActivity { it.onBackPressedDispatcher.onBackPressed() }; compose.waitForIdle() }

    private fun openProjections() {
        tab(tx("Patrimonio", "Wealth"))
        click(tx("Proyecciones", "Projections"))
    }

    @Test fun vipWithKnownInputsSeesTheFourHorizons() {
        launch()
        openProjections()
        listOf(1, 3, 6, 12).forEach { months -> waitUntil("point $months") { reveal("projections.point.$months") } }
        assertFalse(tagged("projections.incomplete"))
        assertFalse(tagged("projections.lowConfidence"))
    }

    @Test fun incompleteProjectionShowsNoFigureAndLinksToTheExistingScreens() {
        launch(fixtures = "EMPTY")
        openProjections()
        waitUntil("incomplete") { tagged("projections.incomplete") }
        listOf(1, 3, 6, 12).forEach { assertFalse("$it", tagged("projections.point.$it")) }
        assertFalse(present(tx("Patrimonio neto", "Net worth")))  // no figure from an unknown
        listOf("income" to tx("Ingresos y base", "Income and base"), "essential_expenses" to tx("Ingresos y base", "Income and base"),
            "savings" to tx("Tus ahorros", "Your savings")).forEach { (code, title) ->
            clickTag("projections.missing.$code")
            waitUntil("$code → $title") { present(title) && !tagged("projections.incomplete") }
            back()
            waitUntil("back to projections") { tagged("projections.incomplete") }
        }
        assertFalse(tagged("projections.missing.debt_payments"))  // the account has no debt
    }

    @Test fun hoyShowsNoProjection() {
        for (fixtures in listOf("POPULATED", "EMPTY")) {
            launch(fixtures = fixtures)
            waitUntil("Hoy loaded ($fixtures)") { tagged("home.debts") }
            assertTrue(fixtures, !present("proyecci"))
        }
    }

    // UX-14 / I09 — the charts.

    @Test fun aCompleteProjectionShowsTheChartsAndKeepsTheCards() {
        for (role in listOf(null, "owner")) {
            launch()
            if (role != null) {
                scenario?.close()
                val intent = android.content.Intent(androidx.test.core.app.ApplicationProvider.getApplicationContext(), MainActivity::class.java)
                    .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L)
                    .putExtra("dincrPlan", "vip").putExtra("dincrRole", role)
                scenario = androidx.test.core.app.ActivityScenario.launch(intent)
            }
            openProjections()
            listOf("cash", "debt", "netWorth").forEach { kind -> waitUntil("$role chart $kind") { reveal("projections.chart.$kind") } }
            // TalkBack: the chart says its title and every point.
            val cash = tx("Efectivo proyectado", "Projected cash")
            val spoken = compose.onAllNodes(androidx.compose.ui.test.hasContentDescription(cash, substring = true), useUnmergedTree = true)
                .fetchSemanticsNodes().flatMap { it.config.getOrNull(androidx.compose.ui.semantics.SemanticsProperties.ContentDescription).orEmpty() }.joinToString()
            listOf(tx("1 mes", "1 month"), tx("12 meses", "12 months")).forEach { assertTrue("$role: $it in $spoken", spoken.contains(it)) }
            // The cards stay as the text alternative.
            listOf(1, 3, 6, 12).forEach { months -> waitUntil("$role card $months") { reveal("projections.point.$months") } }
        }
    }

    @Test fun anIncompleteProjectionShowsNoChart() {
        launch(fixtures = "EMPTY")
        openProjections()
        waitUntil("incomplete") { tagged("projections.incomplete") }
        listOf("cash", "debt", "netWorth").forEach { assertFalse(it, tagged("projections.chart.$it")) }
    }

    @Test fun freeAndBasicKeepProjectionsLocked() {
        for (plan in listOf("free", "basic")) {
            launch(plan = plan)
            tab(tx("Patrimonio", "Wealth"))
            waitUntil("locked ($plan)") { present(tx("Disponible desde VIP", "Available from VIP")) }
            click(tx("Proyecciones", "Projections"))
            waitUntil("Suscripción ($plan)") { present(tx("Suscripción actual", "Current subscription")) }
            assertFalse(tagged("projections.chart.cash"))
        }
    }
}
