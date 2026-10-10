package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.performTextInput
import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Rule
import org.junit.Test

/**
 * SEC-01 — the server refuses work until the current terms are accepted (`auth/legal.py`). When the
 * terms change while the app is open, the next change answers 403 `legal_acceptance_required`: the
 * app reads the identity again and shows the acceptance screen instead of leaving a bare "no
 * permission" message. Once accepted, changes run as before. iOS twin: `LegalGateUITests`.
 * FakeBackend only ([com.dincr.data.FakeBackend.legalLapses]).
 */
class LegalGateUiTest {
    @get:Rule val compose = createEmptyComposeRule()
    private var scenario: ActivityScenario<MainActivity>? = null

    @After fun close() { scenario?.close() }

    private fun present(text: String) = compose.onAllNodes(hasText(text, substring = true), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
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
    private fun payTheCard() {
        click(tx("Deudas", "Debts"))
        click(tx("Registrar pago", "Record payment"))
        waitUntil("the amount dialog") { present(tx("Pendiente:", "Outstanding:")) }
        compose.onAllNodes(hasText(tx("Monto", "Amount"))).onFirst().performTextInput("10.000")
        click(tx("Registrar", "Record"))
    }

    @Test fun termsThatChangeWhileOpenBringBackTheAcceptanceScreen() {
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L)
        scenario = ActivityScenario.launch(intent)
        waitUntil("Hoy") { present(tx("Resultado del mes", "This month’s result")) }
        scenario!!.onActivity { ViewModelProvider(it)[AppModel::class.java].fixtureBackend!!.legalLapses = true }

        payTheCard()
        waitUntil("the acceptance screen") { present(tx("Antes de seguir", "Before you continue")) }
        click(tx("Acepto los Términos y Condiciones", "I accept the Terms and Conditions"))
        click(tx("Acepto la Política de Privacidad", "I accept the Privacy Policy"))
        click(tx("Aceptar y continuar", "Accept and continue"))
        waitUntil("Hoy again") { present(tx("Resultado del mes", "This month’s result")) }

        payTheCard()
        waitUntil("accepted: changes run again") { present(tx("Pago registrado", "Payment recorded")) }
    }
}
