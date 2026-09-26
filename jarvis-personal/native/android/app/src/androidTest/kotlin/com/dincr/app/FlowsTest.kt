package com.dincr.app

import android.content.Intent
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isRoot
import androidx.compose.ui.test.printToLog
import org.junit.After
import androidx.compose.ui.test.junit4.AndroidComposeTestRule
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import java.util.Locale
import org.junit.Before
import org.junit.Rule
import org.junit.Test

/** End-to-end flows on synthetic fixture data, mirroring the iOS DINCRUITests. */
class FlowsTest {
    @get:Rule val compose = createEmptyComposeRule()

    @Before fun spanish() { Locale.setDefault(Locale.forLanguageTag("es-CR")) }

    private var scenario: ActivityScenario<MainActivity>? = null

    /** Spinners and crossfades never let Compose go idle, so the test clock is driven explicitly. */
    private fun advance() { compose.mainClock.advanceTimeBy(100) }

    @After fun close() { scenario?.close() }

    private fun launch(fixture: String = "POPULATED", skipLogin: Boolean = true): ActivityScenario<MainActivity> {
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", fixture).putExtra("dincrSkipLogin", skipLogin).putExtra("dincrLatencyMs", 0L)
        return ActivityScenario.launch<MainActivity>(intent).also { scenario = it }
    }

    private fun waitForText(text: String, timeout: Long = 15_000) {
        try {
            compose.waitUntil(timeout) { advance(); compose.onAllNodes(hasText(text), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }
        } catch (error: Throwable) {
            runCatching { compose.onAllNodes(isRoot()).printToLog("DINCR-UI") }
            throw error
        }
    }

    @Test fun loginLeadsToHome() {
        launch(skipLogin = false)
        compose.waitUntil(15_000) { advance(); compose.onAllNodes(hasTestTag("login.google")).fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("login.google").performClick()
        waitForText("Disponible este mes")
    }

    @Test fun homeShowsKeyFigureAndSections() {
        launch()
        waitForText("Disponible este mes")
        compose.onNodeWithText("Ingresos y gastos").assertExists()
    }

    @Test fun addExpenseRejectsAmbiguousAmountThenSaves() {
        launch()
        waitForText("Disponible este mes")
        compose.onNodeWithText("Movimientos").performClick()
        compose.waitUntil(15_000) { advance(); compose.onAllNodes(hasTestTag("movements.add")).fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("movements.add").performClick()
        compose.onNodeWithTag("editor.save").performClick()
        waitForText("Revisá 2 campos")
        compose.onNodeWithTag("editor.amount").performTextInput("1.5.2")
        compose.onNodeWithTag("editor.description").performTextInput("Panadería")
        compose.onNodeWithTag("editor.save").performClick()
        compose.waitUntil(15_000) { advance(); compose.onAllNodes(hasText("Escribí un monto", substring = true)).fetchSemanticsNodes().isNotEmpty() }
    }

    @Test fun emptyAccountTeachesTheFirstAction() {
        launch("EMPTY")
        waitForText("Todavía no hay movimientos")
    }

    @Test fun failingBackendShowsRecovery() {
        launch("FAILING")
        waitForText("No pudimos cargar tu cuenta")
        compose.onNodeWithText("Intentar de nuevo").assertExists()
    }

    @Test fun newUserGoesThroughProfileSetup() {
        launch("NEW_USER")
        compose.waitUntil(15_000) { advance(); compose.onAllNodes(hasTestTag("setup.continue")).fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithTag("setup.continue").performClick()
        compose.onNodeWithText("Tomar control de mis finanzas").performClick()
        compose.onNodeWithTag("setup.continue").performClick()
        compose.onNodeWithTag("setup.continue").performClick()
        compose.onNodeWithTag("setup.continue").performClick()
        waitForText("Disponible este mes")
    }
}
