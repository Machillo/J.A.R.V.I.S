package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isRoot
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextClearance
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.printToLog
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Rule
import org.junit.Test

/**
 * End-to-end flows on synthetic fixture data, mirroring the iOS DINCRUITests. Copy is resolved
 * with the app's own `tx` after launch: Android resets the process locale from the device
 * configuration when the activity starts, so the tests pass on Spanish and English devices.
 */
class FlowsTest {
    @get:Rule val compose = createEmptyComposeRule()

    private var scenario: ActivityScenario<MainActivity>? = null

    /** Spinners and crossfades never let Compose go idle, so the test clock is driven explicitly. */
    private fun advance() { compose.mainClock.advanceTimeBy(100) }

    @After fun close() { scenario?.close() }

    private fun launch(fixture: String = "POPULATED", skipLogin: Boolean = true): ActivityScenario<MainActivity> {
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", fixture).putExtra("dincrSkipLogin", skipLogin).putExtra("dincrLatencyMs", 0L)
        return ActivityScenario.launch<MainActivity>(intent).also { scenario = it }
    }

    private fun waitUntil(what: String, condition: () -> Boolean) {
        try {
            compose.waitUntil(15_000) { advance(); condition() }
        } catch (error: Throwable) {
            runCatching { compose.onAllNodes(isRoot()).printToLog("DINCR-UI") }
            throw AssertionError("timed out waiting for $what", error)
        }
    }

    private fun waitForText(text: String, substring: Boolean = false) =
        waitUntil("\"$text\"") { compose.onAllNodes(hasText(text, substring = substring), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }

    private fun waitForGone(text: String) =
        waitUntil("\"$text\" to disappear") { compose.onAllNodes(hasText(text), useUnmergedTree = true).fetchSemanticsNodes().isEmpty() }

    private fun waitForTag(tag: String) =
        waitUntil("tag $tag") { compose.onAllNodes(hasTestTag(tag)).fetchSemanticsNodes().isNotEmpty() }

    private fun openMovements() {
        waitForText(tx("Disponible este mes", "Available this month"))
        compose.onNodeWithText(tx("Movimientos", "Transactions")).performClick()
        waitForTag("movements.add")
    }

    @Test fun loginLeadsToHome() {
        launch(skipLogin = false)
        waitForTag("login.google")
        compose.onNodeWithTag("login.google").performClick()
        waitForText(tx("Disponible este mes", "Available this month"))
    }

    @Test fun homeShowsKeyFigureAndSections() {
        launch()
        waitForText(tx("Disponible este mes", "Available this month"))
        compose.onNodeWithText(tx("Ingresos y gastos", "Income and expenses")).assertExists()
        compose.onNodeWithText(tx("En qué se va el dinero", "Where the money goes")).assertExists()
    }

    @Test fun addExpenseRejectsAmbiguousAmountThenSaves() {
        launch()
        openMovements()
        compose.onNodeWithTag("movements.add").performClick()
        compose.onNodeWithTag("editor.save").performClick()
        waitForText(tx("Revisá 2 campos", "Check 2 fields"))
        compose.onNodeWithTag("editor.amount").performTextInput("1.5.2")
        compose.onNodeWithTag("editor.description").performTextInput("Panadería")
        compose.onNodeWithTag("editor.save").performClick()
        waitForText(tx("Escribí un monto", "Enter an amount"), substring = true)
        compose.onNodeWithTag("editor.amount").performTextClearance()
        compose.onNodeWithTag("editor.amount").performTextInput("4.250")
        compose.onNodeWithTag("editor.save").performClick()
        waitForText("Panadería")
        waitForGone(tx("Nuevo movimiento", "New transaction"))
        val rows = compose.onAllNodesWithText("Panadería").fetchSemanticsNodes().size
        check(rows == 1) { "one saved row expected, found $rows" }
    }

    /** Saving only a new description must keep the stored cents and the stored category. */
    @Test fun editKeepsTheStoredAmountAndCategory() {
        launch()
        openMovements()
        compose.onNodeWithText("Feria del agricultor").performClick()
        waitForTag("editor.amount")
        compose.onNodeWithTag("editor.amount").assert(hasText("12.345,5"))
        val categoryField = compose.onAllNodesWithText("Feria", useUnmergedTree = true).fetchSemanticsNodes()
            .any { it.config.contains(SemanticsProperties.EditableText) }
        check(categoryField) { "the stored category must stay selected in the editor" }
        compose.onNodeWithTag("editor.description").performTextClearance()
        compose.onNodeWithTag("editor.description").performTextInput("Feria de Zapote")
        compose.onNodeWithTag("editor.save").performClick()
        waitForText("Feria de Zapote")
        waitForGone(tx("Editar movimiento", "Edit transaction"))
        compose.onNodeWithText("Feria de Zapote").performClick()
        waitForTag("editor.amount")
        compose.onNodeWithTag("editor.amount").assert(hasText("12.345,5"))
    }

    @Test fun deleteAsksAndRemovesTheRow() {
        launch()
        openMovements()
        compose.onNodeWithText("Feria del agricultor").performClick()
        waitForText(tx("Eliminar movimiento", "Delete transaction"))
        compose.onNodeWithText(tx("Eliminar movimiento", "Delete transaction")).performClick()
        waitForText(tx("Esta acción no se puede deshacer.", "This can’t be undone."))
        compose.onNodeWithText(tx("Eliminar", "Delete")).performClick()
        waitForGone("Feria del agricultor")
    }

    @Test fun emptyAccountTeachesTheFirstAction() {
        launch("EMPTY")
        waitForText(tx("Todavía no hay movimientos", "No transactions yet"))
    }

    @Test fun failingBackendShowsRecovery() {
        launch("FAILING")
        waitForText(tx("No pudimos cargar tu cuenta", "We couldn’t load your account"))
        compose.onNodeWithText(tx("Intentar de nuevo", "Try again")).assertExists()
    }

    @Test fun newUserGoesThroughProfileSetup() {
        launch("NEW_USER")
        waitForTag("setup.continue")
        compose.onNodeWithTag("setup.continue").performClick()
        compose.onNodeWithText(tx("Tomar control de mis finanzas", "Take control of my finances")).performClick()
        compose.onNodeWithTag("setup.continue").performClick()
        compose.onNodeWithTag("setup.continue").performClick()
        compose.onNodeWithTag("setup.continue").performClick()
        waitForText(tx("Disponible este mes", "Available this month"))
    }
}
