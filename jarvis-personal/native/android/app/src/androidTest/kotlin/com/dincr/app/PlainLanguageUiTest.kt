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
import org.junit.Assert.assertFalse
import org.junit.Rule
import org.junit.Test

/**
 * UX-16 — plain financial language: the money left after commitments has one name everywhere (no
 * "margen"), and the monthly review says how each indicator moved in words, with its unit. Copy is
 * resolved with the app's own `tx` (the device language). iOS twin: `PlainLanguageUITests`.
 */
class PlainLanguageUiTest {
    @get:Rule val compose = createEmptyComposeRule()
    private var scenario: ActivityScenario<MainActivity>? = null

    private fun launch(plan: String) {
        scenario?.close()
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan)
        scenario = ActivityScenario.launch(intent)
    }

    @After fun close() { scenario?.close() }

    private fun present(text: String) = compose.onAllNodes(hasText(text, substring = true), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    private fun waitUntil(what: String, condition: () -> Boolean) {
        repeat(150) { if (condition()) return; Thread.sleep(100); compose.waitForIdle() }
        throw AssertionError("timed out waiting for $what")
    }
    private fun click(text: String) {
        waitUntil("\"$text\"") { present(text) }
        val clickable = compose.onAllNodes(hasText(text) and hasClickAction())
        val node = if (clickable.fetchSemanticsNodes().isNotEmpty()) clickable.onFirst() else compose.onAllNodes(hasText(text)).onFirst()
        runCatching { node.performScrollTo() }
        node.performSemanticsAction(SemanticsActions.OnClick)
    }
    private fun tab(text: String) {
        waitUntil("tab $text") { compose.onAllNodes(hasText(text) and isSelectable()).fetchSemanticsNodes().isNotEmpty() }
        compose.onAllNodes(hasText(text) and isSelectable()).onFirst().performSemanticsAction(SemanticsActions.OnClick)
    }
    private val noMargin get() = listOf("Margen", "margin", "Margin")

    @Test fun hoySaysWhatIsLeft() {
        launch("vip")
        waitUntil("left after commitments") { present(tx("Libre después de compromisos", "Left after commitments")) }
        noMargin.forEach { assertFalse(it, present(it)) }
    }

    @Test fun basicPlanNamesWhatIsLeft() {
        launch("basic")
        tab(tx("Plan", "Plan"))
        click(tx("Tu plan del mes", "Your plan for the month"))
        waitUntil("left after your commitments") { present(tx("Libre después de tus compromisos", "Left after your commitments")) }
        noMargin.forEach { assertFalse(it, present(it)) }
    }

    @Test fun theMonthlyReviewSaysHowEachIndicatorMoved() {
        launch("vip")
        tab(tx("Movimientos", "Transactions"))
        click(tx("Análisis", "Analysis"))
        click(tx("Revisión del mes", "Monthly review"))
        // The fixture's labels are the backend's Spanish ones; the trend words and units are the app's.
        waitUntil("debt") { present("Deuda total · ${tx("mejoró", "improved")}") }
        waitUntil("coverage") { present("Meses que cubre tu fondo de emergencia · ${tx("sin cambios", "no change")}") }
        waitUntil("one month") { present(tx("1 mes", "1 month")) }
        waitUntil("flow") { present("Ingresos menos gastos · ${tx("empeoró", "got worse")}") }
    }
}
