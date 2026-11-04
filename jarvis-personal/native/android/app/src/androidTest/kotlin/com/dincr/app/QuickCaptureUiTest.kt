package com.dincr.app

import android.content.Intent
import androidx.compose.ui.test.assertTextContains
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import com.dincr.data.QuickAction
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/** Sharing a bank's text prefills the new expense, and the tile and widget's intent opens it. Invented text only. */
class QuickCaptureUiTest {
    @get:Rule val compose = createEmptyComposeRule()

    private var scenario: ActivityScenario<MainActivity>? = null

    @After fun close() { scenario?.close() }

    private fun launch(action: String, text: String? = null) {
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java).setAction(action)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", "vip")
        text?.let { intent.setType("text/plain").putExtra(Intent.EXTRA_TEXT, it) }
        scenario = ActivityScenario.launch(intent)
        compose.waitUntil(20_000) { compose.onAllNodes(hasTestTag("editor.amount")).fetchSemanticsNodes().isNotEmpty() }
    }

    @Test fun sharingATextPrefillsTheNewExpenseAndRecordsNothing() {
        launch(Intent.ACTION_SEND, "Compra por ₡18.450,00 en SUPER EJEMPLO aprobada")
        compose.onNodeWithTag("editor.amount").assertTextContains("18.450", substring = true)
        assertTrue(compose.onAllNodes(hasTestTag("editor.amount")).fetchSemanticsNodes().size == 1)
    }

    @Test fun theTileAndWidgetActionOpensANewExpense() {
        launch(QuickAction.NEW_EXPENSE.intentAction)
        compose.onNodeWithTag("editor.amount").assertExists()
    }
}
