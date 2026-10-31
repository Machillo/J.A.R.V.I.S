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
import org.junit.Rule
import org.junit.Test

/**
 * AG-1 — Plan → Aguinaldo (the Owner's, read from mail): under the accrued amount, "¿En qué usarlo?"
 * lists the fixed split with why. iOS twin: `AguinaldoPlanUITests`. FakeBackend only.
 */
class AguinaldoPlanUiTest {
    @get:Rule val compose = createEmptyComposeRule()
    private var scenario: ActivityScenario<MainActivity>? = null

    @After fun close() { scenario?.close() }

    private fun present(text: String) = compose.onAllNodes(hasText(text, substring = true), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    private fun waitUntil(what: String, condition: () -> Boolean) {
        repeat(150) { if (condition()) return; Thread.sleep(100); compose.waitForIdle() }
        throw AssertionError("timed out waiting for $what")
    }
    private fun click(text: String, selectable: Boolean = false) {
        val matcher = if (selectable) hasText(text) and isSelectable() else hasText(text) and hasClickAction()
        waitUntil(text) { compose.onAllNodes(matcher).fetchSemanticsNodes().isNotEmpty() }
        val node = compose.onAllNodes(matcher).onFirst()
        runCatching { node.performScrollTo() }
        node.performSemanticsAction(SemanticsActions.OnClick)
    }

    @Test fun theOwnerSeesWhatToUseTheAguinaldoFor() {
        scenario = ActivityScenario.launch(Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L)
            .putExtra("dincrPlan", "vip").putExtra("dincrRole", "owner"))
        click(tx("Plan", "Plan"), selectable = true)
        click(tx("Aguinaldo", "Aguinaldo"))
        waitUntil("the plan") { present(tx("¿En qué usarlo?", "What to use it for?")) && present(tx("Diciembre", "Diciembre")) }
    }
}
