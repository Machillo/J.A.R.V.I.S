package com.dincr.app

import android.content.Intent
import androidx.compose.ui.test.assertIsOff
import androidx.compose.ui.test.assertIsOn
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Rule
import org.junit.Test

/** Plan → Tu plan del mes: a VIP chooses whether investing is in the plan; Basic doesn't have it. iOS: `InvestmentChoiceUITests`. */
class InvestmentChoiceUiTest {
    @get:Rule val compose = createEmptyComposeRule()

    private var scenario: ActivityScenario<MainActivity>? = null

    @After fun close() { scenario?.close() }

    private fun openPlan(plan: String) {
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan)
        scenario = ActivityScenario.launch(intent)
        compose.waitUntil(15_000) { compose.onAllNodes(hasText(tx("Plan", "Plan"))).fetchSemanticsNodes().isNotEmpty() }
        compose.onAllNodes(hasText(tx("Plan", "Plan"))).onFirst().performClick()
        compose.waitUntil(15_000) { compose.onAllNodes(hasText(tx("Tu plan del mes", "Your plan for the month"))).fetchSemanticsNodes().isNotEmpty() }
        compose.onAllNodes(hasText(tx("Tu plan del mes", "Your plan for the month"))).onFirst().performClick()
    }

    private fun waitForChoice() = compose.waitUntil(15_000) { compose.onAllNodes(hasTestTag("plan.investmentChoice")).fetchSemanticsNodes().isNotEmpty() }

    @Test fun aVipTurnsItOn() {
        openPlan("vip")
        waitForChoice()
        val choice = compose.onNodeWithTag("plan.investmentChoice")
        compose.waitForIdle()
        choice.performScrollTo().assertIsOff()
        choice.performClick()
        compose.waitForIdle()
        choice.assertIsOn()
    }

    @Test fun basicDoesNotHaveIt() {
        openPlan("basic")
        compose.waitUntil(15_000) { compose.onAllNodes(hasTestTag("plan.month.preferences")).fetchSemanticsNodes().isEmpty() }
        Thread.sleep(1500)
        compose.onNodeWithTag("plan.investmentChoice").assertDoesNotExist()
    }
}
