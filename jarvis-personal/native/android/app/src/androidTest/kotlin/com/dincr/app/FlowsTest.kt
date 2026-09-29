package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.hasScrollToNodeAction
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isRoot
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onLast
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performTextClearance
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.printToLog
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Rule
import org.junit.Test

/**
 * End-to-end flows on synthetic data served by the in-memory FakeBackend (Debug only), through the
 * real API client. Copy is resolved with the app's own `tx` after launch, so the tests pass on
 * Spanish and English devices.
 */
class FlowsTest {
    @get:Rule val compose = createEmptyComposeRule()

    private var scenario: ActivityScenario<MainActivity>? = null

    /** Spinners and crossfades never let Compose go idle, so the test clock is driven explicitly. */
    private fun advance() { compose.mainClock.advanceTimeBy(100) }

    @After fun close() { scenario?.close() }

    private fun launch(fixture: String = "POPULATED", skipLogin: Boolean = true, plan: String = "free"): ActivityScenario<MainActivity> {
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", fixture).putExtra("dincrSkipLogin", skipLogin).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan)
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

    private fun click(text: String) {
        waitForText(text)
        val node = compose.onAllNodesWithText(text).onFirst()
        runCatching { node.performScrollTo() } // dialogs have nothing to scroll
        node.performClick()
    }

    /** Rows below the fold of a lazy list exist only once scrolled to. */
    private fun rowText(text: String) = compose.onNode(hasScrollToNodeAction()).performScrollToNode(hasText(text)).let { compose.onNodeWithText(text) }

    private fun tab(label: String) = compose.onAllNodesWithText(label).onFirst().performClick()

    private fun openMovements() {
        waitForText(tx("Disponible este mes", "Available this month"))
        tab(tx("Movimientos", "Transactions"))
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
        compose.onNodeWithText(tx("Ingresos y gastos", "Income and expenses")).performScrollTo()
        compose.onNodeWithText(tx("En qué se va el dinero", "Where the money goes")).performScrollTo()
    }

    @Test fun addExpenseRejectsAmbiguousAmountThenSaves() {
        launch()
        openMovements()
        compose.onNodeWithTag("movements.add").performClick()
        compose.onNodeWithTag("editor.save").performScrollTo().performClick()
        waitForText(tx("Revisá 2 campos", "Check 2 fields"))
        compose.onNodeWithTag("editor.amount").performTextInput("1.5.2")
        compose.onNodeWithTag("editor.description").performTextInput("Panadería")
        compose.onNodeWithTag("editor.save").performScrollTo().performClick()
        waitForText(tx("Escribí un monto", "Enter an amount"), substring = true)
        compose.onNodeWithTag("editor.amount").performTextClearance()
        compose.onNodeWithTag("editor.amount").performTextInput("4.250")
        compose.onNodeWithTag("editor.save").performScrollTo().performClick()
        waitForText("Panadería")
        waitForGone(tx("Nuevo movimiento", "New transaction"))
        val rows = compose.onAllNodesWithText("Panadería").fetchSemanticsNodes().size
        check(rows == 1) { "one saved row expected, found $rows" }
    }

    /** A dollar expense needs the user's own rate and is recorded in colones with the preview. */
    @Test fun dollarExpenseAsksForTheRate() {
        launch()
        openMovements()
        compose.onNodeWithTag("movements.add").performClick()
        click(tx("Dólares", "Dollars"))
        compose.onNodeWithTag("editor.amount").performTextInput("10")
        compose.onNodeWithTag("editor.description").performTextInput("Libro en línea")
        // Prefilled with the user's latest own rate (never a market rate); cleared, it is required.
        compose.onNodeWithTag("editor.rate").assert(hasText("507,5"))
        compose.onNodeWithTag("editor.rate").performTextClearance()
        compose.onNodeWithTag("editor.save").performScrollTo().performClick()
        waitForText(tx("Escribí cuántos colones vale 1 dólar", "Enter how many colones 1 dollar is worth"), substring = true)
        compose.onNodeWithTag("editor.rate").performTextInput("507,5")
        waitForText(tx("Se registra como ₡5.075", "Recorded as ₡5.075"), substring = true)
        compose.onNodeWithTag("editor.save").performScrollTo().performClick()
        waitForText("Libro en línea")
        waitForText(tx("TC 507,5", "Rate 507,5"), substring = true)
    }

    /** Saving only a new description must keep the stored cents and the stored category. */
    @Test fun editKeepsTheStoredAmountAndCategory() {
        launch()
        openMovements()
        rowText("Feria del agricultor").performClick()
        waitForTag("editor.amount")
        compose.onNodeWithTag("editor.amount").assert(hasText("12.345,5"))
        val categoryField = compose.onAllNodesWithText("Feria", useUnmergedTree = true).fetchSemanticsNodes()
            .any { it.config.contains(SemanticsProperties.EditableText) }
        check(categoryField) { "the stored category must stay selected in the editor" }
        compose.onNodeWithTag("editor.description").performTextClearance()
        compose.onNodeWithTag("editor.description").performTextInput("Feria de Zapote")
        compose.onNodeWithTag("editor.save").performScrollTo().performClick()
        waitForText("Feria de Zapote")
        waitForGone(tx("Editar movimiento", "Edit transaction"))
        rowText("Feria de Zapote").performClick()
        waitForTag("editor.amount")
        compose.onNodeWithTag("editor.amount").assert(hasText("12.345,5"))
    }

    /** A row typed in dollars is edited in dollars with its own rate, never silently converted. */
    @Test fun dollarRowKeepsItsOriginalAmountAndRate() {
        launch()
        openMovements()
        rowText("Suscripción en dólares").performClick()
        waitForTag("editor.amount")
        compose.onNodeWithTag("editor.amount").assert(hasText("10"))
        compose.onNodeWithTag("editor.rate").assert(hasText("507,5"))
        compose.onNodeWithTag("editor.description").performTextClearance()
        compose.onNodeWithTag("editor.description").performTextInput("Streaming")
        compose.onNodeWithTag("editor.save").performScrollTo().performClick()
        waitForText("Streaming")
        rowText("Streaming").performClick()
        waitForTag("editor.amount")
        compose.onNodeWithTag("editor.amount").assert(hasText("10"))
        compose.onNodeWithTag("editor.rate").assert(hasText("507,5"))
    }

    @Test fun deleteAsksAndRemovesTheRow() {
        launch()
        openMovements()
        rowText("Feria del agricultor").performClick()
        waitForText(tx("Eliminar movimiento", "Delete transaction"))
        compose.onNodeWithText(tx("Eliminar movimiento", "Delete transaction")).performClick()
        waitForText(tx("Esta acción no se puede deshacer.", "This can’t be undone."))
        compose.onNodeWithText(tx("Eliminar", "Delete")).performClick()
        waitForGone("Feria del agricultor")
    }

    @Test fun debtPaymentIsRecorded() {
        launch()
        waitForText(tx("Disponible este mes", "Available this month"))
        tab(tx("Plan", "Plan"))
        click(tx("Deudas", "Debts"))
        waitForText("Tarjeta de ejemplo")
        click(tx("Registrar pago", "Record payment"))
        waitForText(tx("Pendiente:", "Outstanding:"), substring = true)
        compose.onAllNodes(hasText(tx("Monto", "Amount"))).onFirst().performTextInput("10.000")
        click(tx("Registrar", "Record"))
        waitForText(tx("Pago registrado", "Payment recorded"))
    }

    @Test fun goalContributionIsRecorded() {
        launch()
        waitForText(tx("Disponible este mes", "Available this month"))
        tab(tx("Plan", "Plan"))
        click(tx("Metas y ahorros", "Goals and savings"))
        waitForText("Fondo de emergencia")
        click(tx("Aportar", "Contribute"))
        compose.onAllNodes(hasText(tx("Monto", "Amount"))).onFirst().performTextInput("5.000")
        // The dialog's own button (the card behind it has one with the same label).
        compose.onAllNodesWithText(tx("Aportar", "Contribute")).onLast().performClick()
        waitForText(tx("Aporte registrado", "Contribution recorded"))
    }

    @Test fun freePlanOffersBasicToolsAsAnUpgrade() {
        launch(plan = "free")
        waitForText(tx("Disponible este mes", "Available this month"))
        tab(tx("Plan", "Plan"))
        waitForText(tx("Disponible desde Basic", "Available from Basic"))
    }

    @Test fun basicPlanShowsTheBudget() {
        launch(plan = "basic")
        waitForText(tx("Balance del mes", "Month balance"))
        tab(tx("Plan", "Plan"))
        click(tx("Presupuesto", "Budget"))
        waitForText(tx("Gastado este mes", "Spent this month"))
        waitForText("Comida")
    }

    @Test fun vipHomeShowsSafeToSpendAndReviewsMail() {
        launch(plan = "vip")
        waitForText(tx("Podés gastar con tranquilidad", "Safe to spend"))
        tab(tx("Perfil", "Profile"))
        click(tx("Correos financieros", "Financial emails"))
        waitForText("Compra en supermercado")
        click(tx("Confirmar", "Confirm"))
        waitForText(tx("Movimiento guardado.", "Transaction saved."))
        // The dollar notice cannot be confirmed as is: it needs the user's rate.
        waitForText(tx("tocá Corregir e indicá tu tipo de cambio", "tap Correct and enter your exchange rate"), substring = true)
    }

    @Test fun legalConsentIsRequiredBeforeTheApp() {
        launch("LEGAL_REQUIRED")
        waitForText(tx("Antes de seguir", "Before you continue"))
        click(tx("Acepto los Términos y Condiciones", "I accept the Terms and Conditions"))
        click(tx("Acepto la Política de Privacidad", "I accept the Privacy Policy"))
        click(tx("Aceptar y continuar", "Accept and continue"))
        waitForText(tx("Disponible este mes", "Available this month"))
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

    @Test fun newUserGoesThroughProfileSetupAndPlan() {
        launch("NEW_USER")
        waitForTag("setup.continue")
        compose.onNodeWithTag("setup.continue").performClick()
        compose.onNodeWithText(tx("Tomar control de mis finanzas", "Take control of my finances")).performClick()
        compose.onNodeWithTag("setup.continue").performClick()
        compose.onNodeWithTag("setup.continue").performClick()
        compose.onNodeWithTag("setup.continue").performClick()
        waitForText(tx("Elegí tu plan", "Choose your plan"))
        click(tx("Elegir Free", "Choose Free"))
        waitForText(tx("Disponible este mes", "Available this month"))
    }
}
