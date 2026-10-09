package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.SemanticsMatcher
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isSelectable
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performSemanticsAction
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import java.time.YearMonth
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * E04 / E05 — Movimientos → Análisis → Resumen del mes draws the month's income vs expenses as bars
 * and its expenses by category as a donut, below the amounts (still there as text). TalkBack reads
 * the bars' amounts and every category with its share. An empty month says so instead of drawing.
 * Every plan reaches the summary; only the Owner keeps the Owner analysis entry. iOS twin:
 * `SummaryChartsUITests`. FakeBackend only.
 */
class SummaryChartsUiTest {
    @get:Rule val compose = createEmptyComposeRule()
    private var scenario: ActivityScenario<MainActivity>? = null

    private fun launch(fixtures: String = "POPULATED", plan: String = "free", role: String? = null) {
        scenario?.close()
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", fixtures).putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan)
        role?.let { intent.putExtra("dincrRole", it) }
        scenario = ActivityScenario.launch(intent)
        tab(tx("Movimientos", "Transactions"))
        clickTag("movements.analysis")
        waitUntil("Análisis") { present(tx("Resumen del mes", "Monthly summary")) }
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
    private fun clickTag(tag: String) {
        waitUntil(tag) { tagged(tag) }
        val node = compose.onAllNodes(hasTestTag(tag) and hasClickAction()).onFirst()
        runCatching { node.performScrollTo() }
        node.performSemanticsAction(SemanticsActions.OnClick)
    }
    /** Content descriptions read by TalkBack inside a tagged block. */
    private fun descriptions(tag: String): List<String> =
        compose.onAllNodes(hasAnyAncestor(hasTestTag(tag)) and SemanticsMatcher("has a description") { it.config.getOrNull(SemanticsProperties.ContentDescription) != null }, useUnmergedTree = true)
            .fetchSemanticsNodes().flatMap { it.config[SemanticsProperties.ContentDescription] }

    private fun thisMonth(): String = shortMonthName(YearMonth.now().monthValue)
    private fun shortMonthName(month: Int) = (if (tx("es", "en") == "es") listOf("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic")
        else listOf("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"))[month - 1]

    @Test fun everyPlanSeesTheBarsAndTheDonutWithTheAmountsKept() {
        for ((plan, role) in listOf("free" to null, "basic" to null, "vip" to null, "vip" to "owner")) {
            val context = role ?: plan
            launch(plan = plan, role = role)
            assertEquals("$context: the Owner entry stays the Owner's", role == "owner", tagged("analysis.owner"))
            click(tx("Resumen del mes", "Monthly summary"))
            // The amounts stay as text above the charts.
            waitUntil("$context: amounts") { present(tx("Balance", "Balance")) }

            waitUntil("$context: E04 bars") { tagged("summary.flow.chart") }
            val bars = descriptions("summary.flow.chart").single()
            val month = thisMonth()
            val expected = Regex("^${Regex.escape(tx("Ingresos y gastos de $month", "Income and expenses for $month"))}\\. $month: " +
                tx("ingresos [0-9]+ colones, gastos [0-9]+ colones$", "income [0-9]+ colones, expenses [0-9]+ colones$"))
            assertTrue("$context: TalkBack names the month and reads both amounts ($bars)", expected.matches(bars))

            compose.onAllNodes(hasTestTag("summary.categories")).onFirst().performScrollTo()
            waitUntil("$context: E05 donut") { descriptions("summary.categories").isNotEmpty() }
            val parts = descriptions("summary.categories")
            assertTrue("$context: TalkBack reads each category with its amount and share ($parts)", parts.any { Regex("^Comida: [0-9]+ colones, [0-9]+ %$").matches(it) })
            assertFalse(context, present(tx("Todavía no hay datos", "No data yet")))
        }
    }

    @Test fun aMonthWithNothingRecordedSaysSoInsteadOfDrawing() {
        launch(fixtures = "EMPTY")
        click(tx("Resumen del mes", "Monthly summary"))
        waitUntil("notice") { tagged("summary.flow.notice") }
        assertTrue(present(tx("Todavía no hay ingresos ni gastos registrados en este mes.", "No income or expenses recorded this month yet.")))
        assertFalse("no bars of nothing", tagged("summary.flow.chart"))
        val categories = tx("Gastos por categoría", "Expenses by category")
        val why = "$categories. ${tx("Todavía no hay datos.", "No data yet.")}"
        waitUntil("the donut says why it isn't drawn") { compose.onAllNodes(hasContentDescription(why), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }
    }

    @Test fun aPreviousMonthDrawsItsOwnSummary() {
        launch()
        click(tx("Resumen del mes", "Monthly summary"))
        waitUntil("bars") { tagged("summary.flow.chart") }
        val previous = tx("Mes anterior", "Previous month")
        repeat(12) {
            compose.onAllNodes(hasContentDescription(previous) and hasClickAction()).onFirst().performSemanticsAction(SemanticsActions.OnClick)
            compose.waitForIdle()
        }
        // A year back the fixture has nothing recorded: the bars give way to the notice.
        waitUntil("notice") { tagged("summary.flow.notice") }
        assertFalse(tagged("summary.flow.chart"))
    }
}
