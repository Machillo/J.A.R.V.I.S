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
 * PR 4 (P6.4) — locked rows instead of hidden ones. §15 PR 10 moved every locked function out of Perfil:
 * Correos and Cuentas to Patrimonio (`WealthUiTest`), Presupuesto and Calendario to Plan → Tu plan del mes
 * (`PlanOrganizeUiTest`), Movimientos recurrentes to Plan → Ingresos y base. Perfil keeps none.
 * iOS twin: `LockedRowsUITests`.
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

    /**
     * §15 PR 10 (option A): Perfil keeps no locked rows: Presupuesto and Calendario are locked inside Plan →
     * Tu plan del mes (`PlanOrganizeUiTest`), Correos and Cuentas in Patrimonio (`WealthUiTest`).
     */
    @Test fun perfilHasNoLockedRowsLeftAndTheOwnerKeepsJarvis() {
        for ((plan, role) in listOf("free" to null, "basic" to null, "vip" to null, "vip" to "owner")) {
            launch(plan, role)
            assertFalse("$plan/$role: locked rows", present(fromBasic) || present(fromVip))
            listOf(budget, calendar, mail, accounts, tx("Movimientos recurrentes", "Recurring transactions")).forEach { assertFalse("$plan/$role: $it", present(it)) }
            assertEquals("$role: JARVIS", role == "owner", present("JARVIS"))
        }
    }
}
