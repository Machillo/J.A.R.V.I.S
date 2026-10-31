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
 * Movimientos → Análisis → Resumen (simple): a month or a year, income, spending and what was saved
 * as text, and two donuts (where the money came from, where it went) that TalkBack reads part by
 * part. An empty period says so. Every plan reaches it. iOS twin: `SummaryChartsUITests`. FakeBackend only.
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

    @Test fun everyPlanSeesTheTotalsAndBothDonuts() {
        for ((plan, role) in listOf("free" to null, "basic" to null, "vip" to null, "vip" to "owner")) {
            val context = role ?: plan
            launch(plan = plan, role = role)
            assertEquals("$context: the financial analysis row", plan != "vip", present(tx("Disponible desde VIP", "Available from VIP")))
            click(tx("Resumen del mes", "Monthly summary"))
            waitUntil("$context: totals") { tagged("summary.income") && tagged("summary.expenses") && tagged("summary.saved") }
            assertEquals("$context: only the Owner has the ledger detail", role == "owner", tagged("summary.owner.detail"))
            assertFalse("$context: no bars any more", tagged("summary.flow.chart"))
            compose.onAllNodes(hasTestTag("summary.incomeSources")).onFirst().performScrollTo()
            waitUntil("$context: where it came from") { descriptions("summary.incomeSources").isNotEmpty() }
            compose.onAllNodes(hasTestTag("summary.categories")).onFirst().performScrollTo()
            waitUntil("$context: where it went") { descriptions("summary.categories").isNotEmpty() }
            val parts = descriptions("summary.categories")
            assertTrue("$context: TalkBack reads each part with its amount and share ($parts)", parts.any { Regex("^Comida: [0-9]+ colones, [0-9]+ %$").matches(it) })
        }
    }

    @Test fun aMonthWithNothingRecordedSaysSo() {
        launch(fixtures = "EMPTY")
        click(tx("Resumen del mes", "Monthly summary"))
        waitUntil("notice") { tagged("summary.flow.notice") }
        assertTrue(present(tx("Todavía no hay ingresos ni gastos registrados en este mes.", "No income or expenses recorded this month yet.")))
    }

    @Test fun theYearHasItsOwnSummary() {
        launch()
        click(tx("Resumen del mes", "Monthly summary"))
        click(tx("Año", "Year"))
        waitUntil("year totals") { tagged("summary.income") }
        val previous = tx("Año anterior", "Previous year")
        repeat(2) {
            compose.onAllNodes(hasContentDescription(previous) and hasClickAction()).onFirst().performSemanticsAction(SemanticsActions.OnClick)
            compose.waitForIdle()
        }
        // Two years back the fixture has nothing recorded.
        waitUntil("notice") { tagged("summary.flow.notice") }
    }
}
