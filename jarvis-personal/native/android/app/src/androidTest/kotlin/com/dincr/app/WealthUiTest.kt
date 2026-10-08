package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.getOrNull
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
import org.junit.Rule
import org.junit.Test

/**
 * §15 PR 8 — Patrimonio: Cuentas and the mail connections (the existing screens; VIP and the Owner,
 * locked below and opening Suscripción), what is owed by debt from Plan → Deudas (every plan), and
 * no net worth figure (K-3). iOS twin: `WealthUITests`. FakeBackend only.
 */
class WealthUiTest {
    @get:Rule val compose = createEmptyComposeRule()
    private var scenario: ActivityScenario<MainActivity>? = null

    private fun launch(plan: String = "free", role: String? = null) {
        scenario?.close()
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan)
        role?.let { intent.putExtra("dincrRole", it) }
        scenario = ActivityScenario.launch(intent)
        tab(wealth)
        waitUntil("Patrimonio") { tagged("wealth.debts") }
    }

    @After fun close() { scenario?.close() }

    private val wealth get() = tx("Patrimonio", "Wealth")
    private fun count(text: String) = compose.onAllNodes(hasText(text, substring = true), useUnmergedTree = true).fetchSemanticsNodes().size
    private fun present(text: String) = count(text) > 0
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
    private fun back() { scenario?.onActivity { it.onBackPressedDispatcher.onBackPressed() }; compose.waitForIdle() }
    private fun selectedTab(): String? = compose.onAllNodes(isSelectable() and isSelected()).fetchSemanticsNodes()
        .firstNotNullOfOrNull { node -> node.config.getOrNull(SemanticsProperties.Text)?.joinToString("") { it.text } }

    private val fromVip get() = tx("Disponible desde VIP", "Available from VIP")
    private val netWorth get() = tx("Patrimonio neto", "Net worth")

    @Test fun freeAndBasicSeeTheirDebtsAndCuentasLocked() {
        for (plan in listOf("free", "basic")) {
            launch(plan)
            waitUntil("debts ($plan)") { tagged("wealth.debts.composition") && present("Tarjeta de ejemplo") }
            // Cuentas, Conexiones de correo, Proyecciones and Escenarios: all locked to VIP.
            assertEquals("$plan: locked rows", 4, count(fromVip))
            assertFalse("K-3: no net worth figure", present(netWorth))
            click(tx("Cuentas", "Accounts"))
            waitUntil("Suscripción ($plan)") { present(tx("Suscripción actual", "Current subscription")) }
        }
    }

    @Test fun debtsAreManagedInPlan() {
        launch()
        clickTag("wealth.debts.manage")
        // Plan → Deudas' own summary (not in Patrimonio).
        waitUntil("Deudas") { present(tx("Cuotas del mes", "Monthly payments")) }
        assertFalse(tagged("wealth.debts.composition"))
    }

    @Test fun vipOpensCuentasAndTheMailConnections() {
        launch("vip")
        assertFalse(present(fromVip))
        click(tx("Conexiones de correo", "Mail connections"))
        waitUntil("the mailbox") { present("ejemplo@correo.test") }
        assertEquals("opened from Patrimonio, it keeps Patrimonio selected", wealth, selectedTab())
        back()
        click(tx("Bancos y cuentas detectados en tus avisos", "Banks and accounts found in your notices"))
        waitUntil("the banks") { present("BAC") }
        assertEquals(wealth, selectedTab())
        back()
        waitUntil("debts") { tagged("wealth.debts.composition") }
        assertFalse("K-3: no net worth figure", present(netWorth))
    }

    @Test fun theOwnerOpensCuentasAndKeepsJarvis() {
        // The fixture seeds the connected mailbox and detected accounts for a VIP launch; the Owner reaches them by role.
        launch("vip", role = "owner")
        click(tx("Bancos y cuentas detectados en tus avisos", "Banks and accounts found in your notices"))
        waitUntil("the banks") { present("BAC") }
        back()
        tab(tx("Perfil", "Profile"))
        waitUntil("JARVIS") { present("JARVIS") }
    }
}
