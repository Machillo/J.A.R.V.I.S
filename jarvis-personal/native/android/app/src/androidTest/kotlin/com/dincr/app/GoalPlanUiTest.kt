package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasText
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
 * GO-1 — Hoy → Metas y ahorros: each goal says what it takes in plain words. A goal with a date says
 * how much per month (one without asks for a date: `GoalPlanTest`); VIP and the Owner also see how long it takes with
 * what is left in a normal month. iOS twin: `GoalPlanUITests`. FakeBackend only.
 */
class GoalPlanUiTest {
    @get:Rule val compose = createEmptyComposeRule()
    private var scenario: ActivityScenario<MainActivity>? = null

    private fun launch(plan: String) {
        scenario?.close()
        scenario = ActivityScenario.launch(Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan))
    }

    @After fun close() { scenario?.close() }

    private fun present(text: String) = compose.onAllNodes(hasText(text, substring = true), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    private fun waitUntil(what: String, condition: () -> Boolean) {
        repeat(150) { if (condition()) return; Thread.sleep(100); compose.waitForIdle() }
        throw AssertionError("timed out waiting for $what")
    }
    private fun openGoals() {
        val goals = tx("Metas y ahorros", "Goals and savings")
        waitUntil("Hoy") { present(goals) }
        val node = compose.onAllNodes(hasText(goals) and hasClickAction()).onFirst()
        runCatching { node.performScrollTo() }
        node.performSemanticsAction(SemanticsActions.OnClick)
        waitUntil("goals") { present("Fondo de emergencia") }
    }

    @Test fun everyPlanSeesWhatEachGoalTakes() {
        launch("free")
        openGoals()
        // The sample goal has a date: it says how much per month.
        waitUntil("per month") { present(tx("necesitás", "you need")) }
        assertFalse("Free has no normal month", present(tx("en un mes normal", "in a normal month")))
    }

    @Test fun vipAlsoSeesHowLongWithItsNormalMonth() {
        launch("vip")
        openGoals()
        waitUntil("how long") { present(tx("Con lo que te sobra en un mes normal", "With what is left in a normal month")) }
    }
}
