package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasScrollToNodeAction
import androidx.compose.ui.test.hasSetTextAction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isSelectable
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.performTextInput
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Assert.assertFalse
import org.junit.Rule
import org.junit.Test

/**
 * Own accounts from the app (Patrimonio → Cuentas): an own account no notice came from is added with its
 * institution, last 4 digits and currency, and any account can be answered "No la reconozco" (never
 * treated as own). FakeBackend only. iOS twin: `OwnAccountsUITests`.
 */
class OwnAccountsUiTest {
    @get:Rule val compose = createEmptyComposeRule()
    private var scenario: ActivityScenario<MainActivity>? = null

    @After fun close() { scenario?.close() }

    private fun present(text: String) = compose.onAllNodes(hasText(text, substring = true), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    private fun tagged(tag: String) = compose.onAllNodes(hasTestTag(tag), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()
    private fun waitUntil(what: String, condition: () -> Boolean) {
        repeat(200) { if (condition()) return; Thread.sleep(100); compose.waitForIdle() }
        // The visible texts, so a failure says what the screen showed instead.
        val texts = runCatching {
            compose.onAllNodes(hasText("", substring = true), useUnmergedTree = true).fetchSemanticsNodes().flatMap { node ->
                (if (node.config.contains(SemanticsProperties.Text)) node.config[SemanticsProperties.Text] else emptyList()).map { it.text }
            }.distinct()
        }.getOrDefault(emptyList())
        throw AssertionError("timed out waiting for $what; screen: $texts")
    }
    private fun reveal(text: String) {
        compose.onAllNodes(hasScrollToNodeAction()).fetchSemanticsNodes().indices.forEach { index ->
            runCatching { compose.onAllNodes(hasScrollToNodeAction())[index].performScrollToNode(hasText(text, substring = true)) }
        }
    }
    private fun click(text: String) {
        waitUntil("\"$text\"") { reveal(text); present(text) }
        // Rows merge their texts into the clickable node: look it up in the merged tree, as a tap would.
        compose.onAllNodes(hasText(text, substring = true) and hasClickAction()).onFirst().performSemanticsAction(SemanticsActions.OnClick)
    }
    private fun clickTag(tag: String) {
        waitUntil(tag) { tagged(tag) }
        compose.onAllNodes(hasTestTag(tag), useUnmergedTree = true).onFirst().performSemanticsAction(SemanticsActions.OnClick)
    }
    private fun openAccounts() {
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", "POPULATED").putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", "vip")
        scenario = ActivityScenario.launch(intent)
        val wealth = tx("Patrimonio", "Wealth")
        waitUntil("tab") { compose.onAllNodes(hasText(wealth) and isSelectable()).fetchSemanticsNodes().isNotEmpty() }
        compose.onAllNodes(hasText(wealth) and isSelectable()).onFirst().performSemanticsAction(SemanticsActions.OnClick)
        click(tx("Cuentas", "Accounts"))
    }

    @Test fun anOwnAccountNoNoticeCameFromIsAddedAndShownAsOwn() {
        openAccounts()
        clickTag("accounts.declare")
        // The form's chip (selectable), not the MultiMoney bank row behind the sheet.
        val chip = hasText("MultiMoney") and isSelectable()
        waitUntil("the institution chips") { compose.onAllNodes(chip).fetchSemanticsNodes().isNotEmpty() }
        compose.onAllNodes(chip).onFirst().performSemanticsAction(SemanticsActions.OnClick)
        val digits = hasSetTextAction() and hasText(tx("Últimos 4 dígitos", "Last 4 digits"), substring = true)
        waitUntil("the digits field") { reveal(tx("Últimos 4 dígitos", "Last 4 digits")); compose.onAllNodes(digits).fetchSemanticsNodes().isNotEmpty() }
        compose.onAllNodes(digits).onFirst().performTextInput("6281")
        click(tx("Dólares", "Dollars"))
        click(tx("Guardar", "Save"))
        waitUntil("the saved notice") { present(tx("Cuenta propia guardada", "Own account saved")) }
        click("MultiMoney")
        waitUntil("the declared account") { present("6281") }
        waitUntil("marked as own") { present(tx("Tuya", "Yours")) }
    }

    @Test fun anAccountCanBeAnsweredIDontRecogniseIt() {
        openAccounts()
        click("BAC Credomatic")
        clickTag("accounts.pending.1")
        waitUntil("the answer") { present(tx("No la reconocés", "You don’t recognise it")) }
        assertFalse("answered: no longer offered", tagged("accounts.pending.1"))
    }
}
