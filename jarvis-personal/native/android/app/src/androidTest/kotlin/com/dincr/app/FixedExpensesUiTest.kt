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
import androidx.compose.ui.test.onLast
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
 * Plan → Gastos fijos (FX-1) on synthetic fixture data: the Owner sees his fixed expenses, adds one and
 * removes one; a VIP manages its recurring expenses there (no type to choose); Basic sees the row locked.
 * iOS: `FixedExpensesUITests`.
 */
class FixedExpensesUiTest {
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

    private fun openFixedExpenses() {
        waitForText(tx("Hoy", "Today"))
        click(tx("Plan", "Plan"))
        click(tx("Gastos fijos", "Fixed expenses"))
    }

    @Test fun theOwnerAddsAndRemovesAFixedExpense() {
        launch(role = "owner")
        openFixedExpenses()
        waitForTag("fixedExpenses.row.9101")
        waitForTag("fixedExpenses.total")
        tapTag("fixedExpenses.add")
        type("fixedExpenses.name", "Agua de ejemplo")
        type("fixedExpenses.amount", "9000")
        click(tx("Guardar", "Save"))
        waitForText("Agua de ejemplo")
        tapTag("fixedExpenses.remove.9101")
        // The dialog's button (the rows have "Quitar" too; the dialog's nodes come last).
        waitForText(tx("¿Quitar «Internet de ejemplo»?", "Remove “Internet de ejemplo”?"))
        compose.onAllNodes(hasText(tx("Quitar", "Remove")) and hasClickAction()).onLast().performSemanticsAction(SemanticsActions.OnClick)
        compose.waitUntil(15_000) { advance(); !tagPresent("fixedExpenses.row.9101") }
    }

    @Test fun aVipManagesItsRecurringExpensesThere() {
        launch()
        openFixedExpenses()
        tapTag("recurring.add")
        waitForText(tx("Nombre", "Name"))
        assertTrue("a fixed expense is always an expense", !present(tx("Ingreso", "Income")))
    }

    @Test fun basicSeesItLocked() {
        launch(plan = "basic")
        waitForText(tx("Hoy", "Today"))
        click(tx("Plan", "Plan"))
        waitForText(tx("Gastos fijos", "Fixed expenses"))
        assertTrue(present(tx("Disponible desde VIP", "Available from VIP")))
    }
}
