package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
import androidx.compose.ui.test.hasAnyAncestor
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isSelectable
import androidx.compose.ui.test.isSelected
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.performScrollTo
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
 * §15 PR 5 (option A) — Plan keeps exactly its six entries, in order. Presupuesto and Calendario
 * financiero are reached inside Tu plan del mes ("Para organizar tu mes", from Basic) and the recurring
 * income and expenses ("Movimientos recurrentes") inside Ingresos y base (every plan); back returns to
 * Plan and Plan stays selected. iOS twin: `PlanOrganizeUITests`. FakeBackend only.
 */
class PlanOrganizeUiTest {
    @get:Rule val compose = createEmptyComposeRule()
    private var scenario: ActivityScenario<MainActivity>? = null

    private fun launch(plan: String = "free", role: String? = null) {
        scenario?.close()
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan)
        role?.let { intent.putExtra("dincrRole", it) }
        scenario = ActivityScenario.launch(intent)
        tab(planTab)
        waitUntil("Plan") { present(tx("Ingresos y base", "Income and base")) }
    }

    @After fun close() { scenario?.close() }

    private val planTab get() = tx("Plan", "Plan")
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
        // The tag wraps the row: click the clickable row inside it.
        val node = compose.onAllNodes(hasAnyAncestor(hasTestTag(tag)) and hasClickAction(), useUnmergedTree = true).onFirst()
        runCatching { node.performScrollTo() }
        node.performSemanticsAction(SemanticsActions.OnClick)
    }
    private fun back() { scenario?.onActivity { it.onBackPressedDispatcher.onBackPressed() }; compose.waitForIdle() }
    private fun selectedTab(): String? = compose.onAllNodes(isSelectable() and isSelected()).fetchSemanticsNodes()
        .firstNotNullOfOrNull { node -> node.config.getOrNull(SemanticsProperties.Text)?.joinToString("") { it.text } }

    private val month get() = tx("Tu plan del mes", "Your plan for the month")
    private val income get() = tx("Ingresos y base", "Income and base")
    private val recurring get() = tx("Movimientos recurrentes", "Recurring transactions")

    @Test fun basicOrganizesTheMonthAndReturnsToThePlan() {
        launch("basic")
        click(month)
        waitUntil("organize") { present(tx("Para organizar tu mes", "To organize your month")) }
        assertFalse(present(tx("Disponible desde Basic", "Available from Basic")))
        clickTag("plan.month.budget")
        // Left Tu plan del mes (its group is gone) for the budget screen.
        waitUntil("Presupuesto") { !tagged("plan.month.budget") && present(tx("Presupuesto", "Budget")) }
        assertEquals(planTab, selectedTab())
        back()
        waitUntil("back in Tu plan del mes") { tagged("plan.month.calendar") }
        clickTag("plan.month.calendar")
        waitUntil("Calendario") { present(tx("Pagos conocidos", "Known payments")) }
        assertEquals(planTab, selectedTab())
        back()
        waitUntil("back in Tu plan del mes") { tagged("plan.month.budget") }
        back()
        waitUntil("back in Plan") { present(income) }
    }

    /** §15 PR 10 (option A): Free opens Tu plan del mes locked and sees Presupuesto and Calendario locked; each opens Suscripción. */
    @Test fun freeOpensTheMonthLockedWithBudgetAndCalendarLocked() {
        launch()
        click(month)
        waitUntil("locked month") { present(tx("Ver suscripciones", "See subscriptions")) && tagged("plan.month.budget") && tagged("plan.month.calendar") }
        assertTrue(present(tx("Para organizar tu mes", "To organize your month")))
        for (tag in listOf("plan.month.budget", "plan.month.calendar")) {
            clickTag(tag)
            waitUntil("Suscripción ($tag)") { present(tx("Suscripción actual", "Current subscription")) }
            assertFalse("$tag: no paid screen", present(tx("Pagos conocidos", "Known payments")) || present(tx("Gastado este mes", "Spent this month")))
            back()
            waitUntil("back in Tu plan del mes") { tagged(tag) }
        }
        back()
        waitUntil("back in Plan") { present(income) }
    }

    @Test fun freeOpensItsRecurringTransactions() {
        launch()
        click(income)
        clickTag("incomeBase.recurring")
        waitUntil("recurring") { present(tx("Gastos fijos por mes", "Fixed expenses per month")) }
        assertEquals(planTab, selectedTab())
        back()
        waitUntil("back in Ingresos y base") { tagged("incomeBase.recurring") }
    }

    @Test fun vipAndOwnerReachEveryAccessAndTheOwnerKeepsJarvis() {
        for ((plan, role) in listOf("vip" to null, "vip" to "owner")) {
            launch(plan, role)
            click(month)
            waitUntil("organize ($role)") { tagged("plan.month.budget") && tagged("plan.month.calendar") }
            back()
            click(income)
            waitUntil("recurring ($role)") { tagged("incomeBase.recurring") }
            back()
            tab(tx("Perfil", "Profile"))
            waitUntil("Perfil") { present(tx("Suscripción", "Subscription")) }
            assertEquals("$role: JARVIS", role == "owner", present("JARVIS"))
        }
    }

    /** §15 PR 10 (option A): Perfil no longer repeats Presupuesto, Calendario or Movimientos recurrentes. */
    @Test fun perfilNoLongerListsFinanzas() {
        for ((plan, role) in listOf("free" to null, "basic" to null, "vip" to null, "vip" to "owner")) {
            launch(plan, role)
            tab(tx("Perfil", "Profile"))
            waitUntil("Perfil ($role)") { present(tx("Suscripción", "Subscription")) }
            listOf(tx("Finanzas", "Finances"), tx("Presupuesto", "Budget"), tx("Calendario financiero", "Financial calendar"), recurring)
                .forEach { assertFalse("$plan/$role: $it", present(it)) }
            assertEquals("$role: JARVIS", role == "owner", present("JARVIS"))
        }
    }

    @Test fun metasYAhorroStaysInHoy() {
        launch()
        tab(tx("Hoy", "Today"))
        waitUntil("Hoy") { tagged("home.goals") }
        tab(planTab)
        waitUntil("Plan") { present(income) }
        assertTrue(!present(tx("Metas y ahorros", "Goals and savings")))
    }
}
