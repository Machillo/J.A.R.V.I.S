package com.dincr.app

import android.content.Intent
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.assert
import androidx.compose.ui.test.hasClickAction
import androidx.compose.ui.test.hasContentDescription
import androidx.compose.ui.test.hasTestTag
import androidx.compose.ui.test.hasScrollToNodeAction
import androidx.compose.ui.test.hasText
import androidx.compose.ui.test.isRoot
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performScrollTo
import androidx.compose.ui.test.performScrollToNode
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.printToLog
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

/**
 * Plan recovery on the FakeBackend (Debug only; synthetic data): the Plan tab's four rows, the
 * relocated screens, the three strategy contracts, Salvavidas, the distribution, Cuentas as the
 * second surface of the mail review, bank logos, the Owner's "Análisis financiero" and the
 * situation form. Copy is resolved with the app's own `tx`, so the tests pass in either language.
 */
class PlanRecoveryUiTest {
    @get:Rule val compose = createEmptyComposeRule()

    private var scenario: ActivityScenario<MainActivity>? = null

    @After fun close() { scenario?.close() }

    private fun launch(plan: String = "free", role: String? = null, fixture: String = "POPULATED") {
        scenario?.close()
        val intent = Intent(ApplicationProvider.getApplicationContext(), MainActivity::class.java)
            .putExtra("dincrFixtures", fixture).putExtra("dincrSkipLogin", true).putExtra("dincrLatencyMs", 0L).putExtra("dincrPlan", plan)
        role?.let { intent.putExtra("dincrRole", it) }
        scenario = ActivityScenario.launch(intent)
    }

    private fun advance() { compose.mainClock.advanceTimeBy(100) }

    private fun present(text: String, substring: Boolean = false) =
        compose.onAllNodes(hasText(text, substring = substring), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty()

    private fun waitUntil(what: String, condition: () -> Boolean) {
        try {
            compose.waitUntil(15_000) { advance(); condition() }
        } catch (error: Throwable) {
            runCatching { compose.onAllNodes(isRoot()).printToLog("DINCR-UI") }
            // The visible texts, so a failure says what the screen showed instead.
            val texts = runCatching {
                compose.onAllNodes(hasText("", substring = true), useUnmergedTree = true).fetchSemanticsNodes().flatMap { node ->
                    (if (node.config.contains(SemanticsProperties.Text)) node.config[SemanticsProperties.Text] else emptyList()).map { it.text }
                }.distinct()
            }.getOrDefault(emptyList())
            throw AssertionError("timed out waiting for $what; screen: $texts", error)
        }
    }

    /** Brings a node into composition and view: lazy lists and small screens (CI emulators) hide it otherwise. */
    private fun scrollTo(text: String, substring: Boolean = false) {
        compose.onAllNodes(hasScrollToNodeAction()).fetchSemanticsNodes().indices.forEach { index ->
            runCatching { compose.onAllNodes(hasScrollToNodeAction())[index].performScrollToNode(hasText(text, substring = substring)) }
        }
    }

    private fun waitForText(text: String, substring: Boolean = false) =
        waitUntil("\"$text\"") { present(text, substring) || run { scrollTo(text, substring); present(text, substring) } }
    private fun waitForTag(tag: String) = waitUntil("tag $tag") { compose.onAllNodes(hasTestTag(tag), useUnmergedTree = true).fetchSemanticsNodes().isNotEmpty() }
    private fun waitForGone(text: String) = waitUntil("\"$text\" to disappear") { !present(text) }

    private fun click(text: String) {
        waitForText(text)
        scrollTo(text)
        // The clickable node itself (a row merges its texts), scrolled into view: a click outside the
        // screen of a small emulator would do nothing.
        val clickable = compose.onAllNodes(hasText(text) and hasClickAction())
        if (clickable.fetchSemanticsNodes().isNotEmpty()) {
            // Invoke the click action itself: on a small screen a row scrolled to the bottom edge sits
            // under the navigation bar, and a tap at its center would hit the bar instead.
            clickable.onFirst().also { runCatching { it.performScrollTo() } }.performSemanticsAction(SemanticsActions.OnClick)
            return
        }
        val node = compose.onAllNodesWithText(text).onFirst()
        runCatching { node.performScrollTo() }
        node.performClick()
    }

    private fun back() = compose.onAllNodes(hasContentDescription(tx("Volver", "Back"))).onFirst().performClick()

    private fun home() = waitForText(tx("Hoy", "Today"))

    private val planRows get() = listOf(tx("Aguinaldo", "Aguinaldo"), tx("Estrategia", "Strategy"), tx("Salvavidas", "Emergency fund"), tx("Distribución de dinero", "Money distribution"))

    @Test fun planHasExactlyFourRowsAndTheRelocatedScreensAreReachable() {
        launch(plan = "basic")
        home()
        // Debts and goals live in Hoy.
        click(tx("Deudas", "Debts"))
        waitForText("Tarjeta de ejemplo")
        back()
        click(tx("Metas y ahorros", "Goals and savings"))
        waitForText("Fondo de emergencia")
        back()
        click(tx("Plan", "Plan"))
        planRows.forEach { waitForText(it) }
        listOf(tx("Deudas", "Debts"), tx("Metas y ahorros", "Goals and savings"), tx("Presupuesto", "Budget"), tx("Cuántos meses te cubre", "How many months it covers"))
            .forEach { assertTrue("$it must not be in Plan", !present(it)) }
        // Basic: Aguinaldo and Salvavidas stay visible, locked from VIP.
        waitForText(tx("Disponible desde VIP", "Available from VIP"))
        // Budget, calendar and recurring live in Perfil → Finanzas.
        click(tx("Perfil", "Profile"))
        waitForText(tx("Finanzas", "Finances"))
        click(tx("Calendario financiero", "Financial calendar"))
        waitForText(tx("Pagos conocidos", "Known payments"))
        back()
        click(tx("Pagos recurrentes", "Recurring payments"))
        waitForText(tx("Gastos fijos por mes", "Fixed expenses per month"))
        // Estrategia left the DINCR tab.
        click("DINCR")
        waitForText(tx("Resumen del mes", "Monthly summary"))
        assertTrue(!present(tx("Estrategia", "Strategy")))
    }

    @Test fun freePlanShowsTheFourRowsLocked() {
        launch(plan = "free")
        home()
        click(tx("Plan", "Plan"))
        planRows.forEach { waitForText(it) }
        waitForText(tx("Disponible desde Basic", "Available from Basic"))
        waitForText(tx("Disponible desde VIP", "Available from VIP"))
        // A locked row opens the plans screen.
        click(tx("Estrategia", "Strategy"))
        waitForText(tx("Plan actual", "Current plan"))
    }

    @Test fun basicStrategySaysTheIncomeIsObservedAndTheDistributionUsesItsAllocations() {
        launch(plan = "basic")
        home()
        click(tx("Plan", "Plan"))
        click(tx("Estrategia", "Strategy"))
        waitForText(tx("Estimado con tus ingresos registrados (no declarado)", "Estimated from your recorded income (not declared)"))
        waitForText(tx("Margen para decidir", "Room to decide"))
        back()
        click(tx("Distribución de dinero", "Money distribution"))
        waitForText(tx("Cómo repartir tu margen", "How to split your margin"))
        waitForText("Extra a la tarjeta")
    }

    @Test fun vipUsersReadTheUsersDashboardAndSalvavidasNeverShowsZero() {
        launch(plan = "vip")
        home()
        click(tx("Plan", "Plan"))
        click(tx("Estrategia", "Strategy"))
        waitForTag("strategy.director.users")
        assertTrue(!present(tx("Tu ciclo", "Your cycle")))
        // The savings were never declared: "Sin dato" in the strategy too.
        compose.onNodeWithText(tx("Sin dato", "No data")).performScrollTo()
        back()
        click(tx("Distribución de dinero", "Money distribution"))
        waitForText(tx("Sobrante a repartir", "Surplus to allocate"))
        waitForText(tx("Gastos registrados", "Recorded spending"))
        assertTrue("Users never see an account cash line", !present(tx("Efectivo disponible ahora", "Cash available now")))
        back()
        click(tx("Salvavidas", "Emergency fund"))
        waitForTag("salvavidas.fund")
        // Unknown savings: "Sin dato" and the way to declare them, never "0 meses".
        waitForText(tx("Sin dato", "No data"))
        waitForText(tx("Completar situación financiera", "Complete financial situation"))
        assertTrue(!present(tx("0 meses", "0 months"), substring = true))
    }

    @Test fun theOwnerReadsTheOwnerStrategy() {
        launch(role = "owner")
        home()
        click(tx("Plan", "Plan"))
        click(tx("Estrategia", "Strategy"))
        waitForTag("strategy.director.owner")
        waitForText(tx("Tu ciclo", "Your cycle"))
        back()
        click(tx("Salvavidas", "Emergency fund"))
        waitForText(tx("Gastos protegidos", "Protected expenses"))
    }

    @Test fun aReviewInCuentasShowsInCorreosAndViceVersa() {
        launch(plan = "vip")
        home()
        click(tx("Perfil", "Profile"))
        // "Cuentas" replaces "Cuentas detectadas".
        assertTrue(!present(tx("Cuentas detectadas", "Detected accounts")))
        click(tx("Cuentas", "Accounts"))
        waitForText("BAC Credomatic")
        waitForTag("bank.logo.bac")
        waitForText(tx("Otras instituciones", "Other institutions"))
        waitForTag("bank.fallback")
        click("BAC Credomatic")
        waitForText("•••• 1234", substring = true)
        waitForText("Compra en supermercado")
        click(tx("Confirmar", "Confirm"))
        waitForText(tx("Confirmado", "Confirmed"))
        back()
        back()
        click(tx("Correos financieros", "Financial emails"))
        waitForText(tx("Por revisar", "To review"))
        waitForText("Tienda en línea")
        assertTrue("confirmed in Cuentas, no longer pending in Correos", !present("Compra en supermercado"))
        // Dismiss in Correos → Cuentas shows it dismissed.
        click(tx("Descartar", "Dismiss"))
        waitForGone("Tienda en línea")
        back()
        click(tx("Cuentas", "Accounts"))
        click("BAC Credomatic")
        waitForText("Tienda en línea")
        waitForText(tx("Descartado", "Dismissed"))
        // A bank whose label differs from its code (account "Banco Popular", candidates "popular").
        back()
        click("Banco Popular")
        waitForText("Transferencia de ejemplo")
    }

    @Test fun onboardingShowsTheBankLogosAndSaysItConnectsNothing() {
        launch(fixture = "NEW_USER")
        waitForTag("setup.continue")
        compose.onNodeWithTag("setup.continue").performClick()
        compose.onNodeWithText(tx("Tomar control de mis finanzas", "Take control of my finances")).performClick()
        compose.onNodeWithTag("setup.continue").performClick()
        compose.onNodeWithTag("setup.continue").performClick()
        waitForText(tx("Esta selección no conecta tus cuentas", "This selection does not connect your accounts"), substring = true)
        listOf("bac", "bn", "bcr", "popular", "davivienda", "davibank", "promerica", "multimoney").forEach { waitForTag("bank.logo.$it") }
        compose.onNodeWithTag("setup.bank.bac").performScrollTo().performClick()
        compose.onNodeWithTag("setup.continue").performClick()
        waitForText(tx("Elegí tu plan", "Choose your plan"))
    }

    @Test fun onlyTheOwnerGetsTheFinancialAnalysis() {
        launch(role = "owner")
        home()
        click(tx("Perfil", "Profile"))
        click("JARVIS")
        click(tx("Análisis financiero", "Financial analysis"))
        waitForTag("analysis.networth")
        waitForText(tx("Patrimonio neto", "Net worth"))
        waitForText(tx("Salud financiera", "Financial health"))
        compose.onNodeWithText(tx("Distribución de gastos", "Spending distribution"), substring = true).performScrollTo()
        compose.onNodeWithText(tx("Gastos por mes", "Expenses by month")).performScrollTo()
        // A VIP user has no JARVIS, so no analysis; admin never enters the public app.
        launch(plan = "vip")
        home()
        click(tx("Perfil", "Profile"))
        waitForText(tx("Mi situación financiera", "My financial situation"))
        assertTrue(!present("JARVIS") && !present(tx("Análisis financiero", "Financial analysis")))
        launch(plan = "vip", role = "admin")
        waitForText(tx("Esta cuenta usa DINCR Owner", "This account uses DINCR Owner"))
        assertTrue(!present(tx("Análisis financiero", "Financial analysis")))
    }

    @Test fun theSituationFormSendsWorkDaysForAFixedIncome() {
        launch(plan = "free")
        home()
        click(tx("Perfil", "Profile"))
        click(tx("Mi situación financiera", "My financial situation"))
        waitForTag("situation.days")
        compose.onNodeWithTag("situation.days").assert(hasText("5"))
        compose.onAllNodes(hasText(tx("Salario mensual", "Monthly salary"))).onFirst().performTextInput("800.000")
        click(tx("Guardar", "Save"))
        // The fake answers 422 without work_days_per_week, like the backend: the saved salary is
        // what the server returns when the screen is opened again.
        repeat(20) { advance(); Thread.sleep(100) } // the in-memory server answers in milliseconds
        back()
        click(tx("Mi situación financiera", "My financial situation"))
        waitUntil("the stored salary") { present("800.000") }
        compose.onNodeWithTag("situation.days").assert(hasText("5"))
    }

    @Test fun basicHomeHasTheHistoryChartAndMovementsShowTheOriginalCurrency() {
        launch(plan = "basic")
        waitForText(tx("Balance del mes", "Month balance"))
        compose.onNodeWithText(tx("Ingresos y gastos", "Income and expenses")).performScrollTo()
        click(tx("Movimientos", "Transactions"))
        // The rate follows the app language's decimal separator (507,5 / 507.5): match what both share.
        waitForText(tx("TC 507", "Rate 507"), substring = true)
    }
}
