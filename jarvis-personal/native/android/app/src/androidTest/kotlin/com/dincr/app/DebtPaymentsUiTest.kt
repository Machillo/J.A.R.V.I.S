package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.performTextInput
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * DEB-07a — Plan → Deudas → "Ver pagos": the payments recorded in DINCR for a debt, newest first,
 * with the amount actually applied. A debt without payments says so. iOS twin:
 * `DebtPaymentsUITests`. FakeBackend only.
 */
class DebtPaymentsUiTest {
    @get:Rule val compose = createEmptyComposeRule()
    private var scenario: ActivityScenario<MainActivity>? = null

    @After fun close() { scenario?.close() }

    private fun present(text: String) = compose.onAllNodes(hasText(text, substring = true), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    private fun tagged(tag: String) = compose.onAllNodes(hasTestTag(tag), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    private fun waitUntil(what: String, condition: () -> Boolean) {
        repeat(150) { if (condition()) return; Thread.sleep(100); compose.waitForIdle() }
        throw AssertionError("timed out waiting for $what")
    }
    private fun click(text: String) {
        waitUntil("\"$text\"") { present(text) }
        val node = compose.onAllNodes(hasText(text) and hasClickAction()).onFirst()
        runCatching { node.performScrollTo() }
        node.performSemanticsAction(SemanticsActions.OnClick)
    }

    @Test fun aRecordedPaymentAppearsInTheDebtsHistory() {
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L)
        scenario = ActivityScenario.launch(intent)
        waitUntil("Hoy") { present(tx("Resultado del mes", "This month’s result")) }
        click(tx("Deudas", "Debts"))
        waitUntil("the debts") { present("Tarjeta de ejemplo") }

        click(tx("Ver pagos", "See payments"))
        waitUntil("no payment yet, said in words") { tagged("debt.payments.empty") }
        click(tx("Cerrar", "Close"))

        click(tx("Registrar pago", "Record payment"))
        waitUntil("the amount dialog") { present(tx("Pendiente:", "Outstanding:")) }
        compose.onAllNodes(hasText(tx("Monto", "Amount"))).onFirst().performTextInput("10.000")
        click(tx("Registrar", "Record"))
        waitUntil("the payment") { present(tx("Pago registrado", "Payment recorded")) }

        click(tx("Ver pagos", "See payments"))
        waitUntil("the history") { tagged("debt.payments.list") }
        assertTrue("the amount applied", present("10.000"))
        assertFalse(tagged("debt.payments.empty"))
    }
}
