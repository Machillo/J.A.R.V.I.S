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
 * K-2 — no public screen shows the financial-health score until it has a canonical calculation
 * (P3.7): Movimientos → Análisis → Revisión del mes keeps its other indicators and its next step
 * but not the score; the Owner keeps it in JARVIS → Análisis financiero. iOS twin:
 * `PublicScoreUITests`. FakeBackend only.
 */
class PublicScoreUiTest {
    @get:Rule val compose = createEmptyComposeRule()
    private var scenario: ActivityScenario<MainActivity>? = null

    private fun launch(plan: String = "free", role: String? = null) {
        scenario?.close()
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan)
        role?.let { intent.putExtra("dincrRole", it) }
        scenario = ActivityScenario.launch(intent)
    }

    @After fun close() { scenario?.close() }

    private fun present(text: String) = compose.onAllNodes(hasText(text, substring = true, ignoreCase = true), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
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

    @Test fun theMonthlyReviewKeepsItsIndicatorsWithoutTheScore() {
        for ((plan, role) in listOf("vip" to null, "free" to "owner")) {
            launch(plan, role)
            tab(tx("Movimientos", "Transactions"))
            click(tx("Análisis", "Analysis"))
            click(tx("Revisión del mes", "Monthly review"))
            // The fixture's lines carry the backend's Spanish labels.
            waitUntil("review ($role)") { present("Deuda total") }
            waitUntil("flow") { present("Flujo operativo") }
            waitUntil("next step") { present("Pagá extra a la tarjeta") }
            for (hidden in listOf("Salud financiera", tx("Salud financiera", "Financial health"), "/100", "de 100", "72.0")) assertFalse("${role ?: plan}: $hidden", present(hidden))
        }
    }

    @Test fun theOwnerKeepsTheScoreInJarvis() {
        launch(role = "owner")
        tab(tx("Perfil", "Profile"))
        click("JARVIS")
        click(tx("Análisis financiero", "Financial analysis"))
        waitUntil("health") { present(tx("Salud financiera", "Financial health")) }
    }
}
