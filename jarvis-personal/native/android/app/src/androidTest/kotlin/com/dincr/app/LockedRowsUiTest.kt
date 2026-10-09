package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isSelectable
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performSemanticsAction
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Rule
import org.junit.Test

/**
 * PR 4 (P6.4) — Perfil never hides a row the subscription does not include: Presupuesto and Calendario
 * are locked below Basic and open Suscripción. VIP and the Owner (by role) open every row, and the Owner
 * keeps JARVIS. §15 PR 10: Correos and Cuentas left Perfil for Patrimonio (locked there below VIP:
 * `WealthUiTest`). iOS twin: `LockedRowsUITests`.
 */
class LockedRowsUiTest {
    @get:Rule val compose = createEmptyComposeRule()
    private var scenario: ActivityScenario<MainActivity>? = null

    private fun launch(plan: String = "free", role: String? = null) {
        scenario?.close()
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan)
        role?.let { intent.putExtra("dincrRole", it) }
        scenario = ActivityScenario.launch(intent)
        tab(tx("Perfil", "Profile"))
        waitUntil("Perfil") { count(tx("Suscripción", "Subscription")) > 0 }
    }

    @After fun close() { scenario?.close() }

    private fun count(text: String) = compose.onAllNodes(hasText(text, substring = true), useUnmergedTree = true).fetchSemanticsNodes().size
    private fun present(text: String) = count(text) > 0
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
    private fun back() { scenario?.onActivity { it.onBackPressedDispatcher.onBackPressed() }; compose.waitForIdle() }

    private val mail get() = tx("Correos financieros", "Financial emails")
    private val accounts get() = tx("Cuentas", "Accounts")
    private val budget get() = tx("Presupuesto", "Budget")
    private val calendar get() = tx("Calendario financiero", "Financial calendar")
    private val fromVip get() = tx("Disponible desde VIP", "Available from VIP")
    private val fromBasic get() = tx("Disponible desde Basic", "Available from Basic")
    private val current get() = tx("Suscripción actual", "Current subscription")

    @Test fun freeSeesBudgetAndCalendarLockedAndALockedRowOpensSuscripcion() {
        launch()
        listOf(budget, calendar, tx("Pagos recurrentes", "Recurring payments")).forEach { waitUntil(it) { present(it) } }
        assertEquals("budget and calendar locked to Basic", 2, count(fromBasic))
        click(budget)
        waitUntil("Suscripción") { present(current) }
    }

    @Test fun basicOpensBudgetAndCalendar() {
        launch("basic")
        listOf(budget, calendar).forEach { waitUntil(it) { present(it) } }
        assertFalse(present(fromBasic) || present(fromVip))
    }

    @Test fun vipAndOwnerOpenEveryRowAndTheOwnerKeepsJarvis() {
        for ((plan, role) in listOf("vip" to null, "vip" to "owner")) {
            launch(plan, role)
            listOf(budget, calendar).forEach { waitUntil("$it ($role)") { present(it) } }
            assertFalse("$role: nothing locked", present(fromVip) || present(fromBasic))
            assertEquals("$role: JARVIS", role == "owner", present("JARVIS"))
        }
    }

    /** §15 PR 10: Correos and Cuentas live in Patrimonio (and Movimientos → Por revisar); Perfil no longer lists them. */
    @Test fun perfilNoLongerListsCorreosOrCuentas() {
        for ((plan, role) in listOf("free" to null, "basic" to null, "vip" to null, "vip" to "owner")) {
            launch(plan, role)
            waitUntil(budget) { present(budget) }
            assertFalse("$plan/$role: Correos", present(mail))
            assertFalse("$plan/$role: Cuentas", present(accounts))
        }
    }
}
