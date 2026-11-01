package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasTestTag
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
 * RT-1 — Plan → Retiro: VIP and the Owner read their retirement savings in simple words; Free and Basic
 * see the row locked. iOS twin: `RetirementUITests`. FakeBackend only.
 */
class RetirementUiTest {
    @get:Rule val compose = createEmptyComposeRule()
    private var scenario: ActivityScenario<MainActivity>? = null

    @After fun close() { scenario?.close() }

    private fun launch(plan: String) {
        scenario?.close()
        scenario = ActivityScenario.launch(Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan))
    }
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

    @Test fun vipReadsItsRetirementSavings() {
        launch("vip")
        click(tx("Plan", "Plan"), selectable = true)
        click(tx("Retiro", "Retirement"))
        waitUntil("the reading") { compose.onAllNodes(hasTestTag("retirement.reading")).fetchSemanticsNodes().isNotEmpty() && present(tx("ahorrado para tu retiro", "saved for retirement")) }
    }

    @Test fun freeSeesItLocked() {
        launch("free")
        click(tx("Plan", "Plan"), selectable = true)
        waitUntil("locked row") { present(tx("Retiro", "Retirement")) && present(tx("Disponible desde VIP", "Available from VIP")) }
    }
}
