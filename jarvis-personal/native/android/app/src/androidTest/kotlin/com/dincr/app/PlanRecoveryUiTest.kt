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
import androidx.compose.ui.test.isSelected
import androidx.compose.ui.test.junit4.createEmptyComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onFirst
import androidx.compose.ui.test.onLast
import androidx.compose.ui.test.performTextClearance
import androidx.compose.ui.test.onNodeWithContentDescription
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
 * second surface of the mail review, bank logos, the Owner's "Análisis financiero" and Plan →
 * Ingresos y base (UX-7: the declared figures; there is no Situación screen). Copy is resolved with the app's own `tx`, so the tests pass in either language.
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

    /** Like [click], by test tag: scrolled into view and the node's own click action, not a tap at its center. */
    private fun tapTag(tag: String) {
        waitForTag(tag)
        compose.onNodeWithTag(tag).also { runCatching { it.performScrollTo() } }.performSemanticsAction(SemanticsActions.OnClick)
    }

    private fun back() = compose.onAllNodes(hasContentDescription(tx("Volver", "Back"))).onFirst().performClick()

    private fun home() = waitForText(tx("Hoy", "Today"))

    private val planRows get() = listOf(tx("Aguinaldo", "Aguinaldo"), tx("Tu plan del mes", "Your plan for the month"), tx("Deudas", "Debts"), tx("Salvavidas", "Emergency fund"), tx("Distribución de dinero", "Money distribution"))

    @Test fun planHasExactlyItsRowsAndTheRelocatedScreensAreReachable() {
        launch(plan = "basic")
        home()
        // Hoy keeps its shortcuts to debts (managed in Plan → Deudas since UX-4) and goals.
        click(tx("Deudas", "Debts"))
        waitForText("Tarjeta de ejemplo")
        // Opened from Hoy, the shared debts screen keeps Hoy selected.
        compose.onNode(hasText(tx("Hoy", "Today")) and isSelected()).assertExists()
        back()
        click(tx("Metas y ahorros", "Goals and savings"))
        waitForText("Fondo de emergencia")
        back()
        click(tx("Plan", "Plan"))
        planRows.forEach { waitForText(it) }
        listOf(tx("Metas y ahorros", "Goals and savings"), tx("Presupuesto", "Budget"), tx("Cuántos meses te cubre", "How many months it covers"))
            .forEach { assertTrue("$it must not be in Plan", !present(it)) }
        // Basic: Aguinaldo and Salvavidas stay visible, locked from VIP.
        waitForText(tx("Disponible desde VIP", "Available from VIP"))
        // Budget, calendar and recurring live in Perfil → Finanzas.
        click(tx("Perfil", "Profile"))
        waitForText(tx("Finanzas", "Finances"))
        click(tx("Calendario financiero", "Financial calendar"))
        waitForText(tx("Pagos conocidos", "Known payments"))
        back()
        click(tx("Movimientos recurrentes", "Recurring transactions"))
        waitForText(tx("Gastos fijos por mes", "Fixed expenses per month"))
        // UX-13: no DINCR tab; the monthly summary lives in Movimientos → Análisis, the plan in Plan.
        assertTrue("no DINCR tab", !present("DINCR"))
        click(tx("Movimientos", "Transactions"))
        click(tx("Análisis", "Analysis"))
        waitForText(tx("Resumen del mes", "Monthly summary"))
        assertTrue(!present(tx("Tu plan del mes", "Your plan for the month")))
        assertTrue(!present(tx("Estrategia", "Strategy")))
    }

    @Test fun freePlanShowsTheFourRowsLocked() {
        launch(plan = "free")
        home()
        click(tx("Plan", "Plan"))
        planRows.forEach { waitForText(it) }
        waitForText(tx("Disponible desde Basic", "Available from Basic"))
        waitForText(tx("Disponible desde VIP", "Available from VIP"))
        // A locked row opens the subscription screen.
        click(tx("Tu plan del mes", "Your plan for the month"))
        waitForText(tx("Suscripción actual", "Current subscription"))
    }

    @Test fun basicStrategySaysTheIncomeIsObservedAndTheDistributionUsesItsAllocations() {
        launch(plan = "basic")
        home()
        click(tx("Plan", "Plan"))
        click(tx("Tu plan del mes", "Your plan for the month"))
        waitForText(tx("Estimado con tus ingresos registrados (no declarado)", "Estimated from your recorded income (not declared)"))
        waitForText(tx("Libre después de tus compromisos", "Left after your commitments"))
        back()
        click(tx("Distribución de dinero", "Money distribution"))
        waitForText(tx("Cómo repartir lo que te queda", "How to split what’s left"))
        waitForText("Extra a la tarjeta")
    }

    @Test fun vipUsersReadTheUsersDashboardAndSalvavidasNeverShowsZero() {
        launch(plan = "vip")
        home()
        click(tx("Plan", "Plan"))
        click(tx("Tu plan del mes", "Your plan for the month"))
        waitForTag("strategy.director.users")
        // UX-3: the strategy's sections are in "Tu plan del mes" → "Ver todo el detalle".
        click(tx("Ver todo el detalle", "See full details"))
        assertTrue(!present(tx("Tu ciclo", "Your cycle")))
        // The savings were never declared: "Sin dato" in the strategy too.
        compose.onNodeWithText(tx("Sin dato", "No data")).performScrollTo()
        back()
        click(tx("Distribución de dinero", "Money distribution"))
        waitForText(tx("Sobrante para repartir", "Surplus to allocate"))
        waitForText(tx("Gastos registrados", "Recorded spending"))
        assertTrue("Users never see an account cash line", !present(tx("Efectivo disponible ahora", "Cash available now")))
        back()
        click(tx("Salvavidas", "Emergency fund"))
        waitForTag("salvavidas.fund")
        // Unknown savings: "Sin dato" and the way to declare them, never "0 meses".
        waitForText(tx("Sin dato", "No data"))
        waitForText(tx("Completar tus ahorros", "Complete your savings"))
        assertTrue(!present(tx("0 meses", "0 months"), substring = true))
    }

    @Test fun theOwnerReadsTheOwnerStrategy() {
        launch(role = "owner")
        home()
        click(tx("Plan", "Plan"))
        click(tx("Tu plan del mes", "Your plan for the month"))
        waitForTag("strategy.director.owner")
        click(tx("Ver todo el detalle", "See full details"))
        waitForText(tx("Tu ciclo", "Your cycle"))
        back()
        click(tx("Salvavidas", "Emergency fund"))
        waitForText(tx("Gastos protegidos", "Protected expenses"))
    }

    /**
     * UX-3 — "Tu plan del mes": the result first (amount to plan, split, one-sentence why), every
     * historical detail one tap away, and Distribución de dinero still reachable on its own row.
     */
    @Test fun theMonthPlanLeadsWithTheResultAndKeepsEveryDetail() {
        launch(plan = "vip")
        home()
        click(tx("Plan", "Plan"))
        click(tx("Tu plan del mes", "Your plan for the month"))
        waitForText(tx("Sobrante para repartir", "Surplus to allocate"))
        waitForText("Atacar deuda:", substring = true)   // the priority, in one sentence (fixture debt name)
        waitForTag("plan.month.split")
        assertTrue("the detail starts closed", !present(tx("Podés gastar con tranquilidad", "Safe to spend")))
        click(tx("¿Por qué DINCR recomienda esto?", "Why does DINCR recommend this?"))
        waitForText(tx("De dónde sale", "Where it comes from"))
        click(tx("Ver todo el detalle", "See full details"))
        waitForText(tx("Podés gastar con tranquilidad", "Safe to spend"))
        assertTrue("Users never see the Owner's cycle", !present(tx("Tu ciclo", "Your cycle")))
        assertTrue("Users never see an account cash line", !present(tx("Efectivo disponible ahora", "Cash available now")))
        back()
        click(tx("Distribución de dinero", "Money distribution"))
        waitForText(tx("Sobrante para repartir", "Surplus to allocate"))
    }

    /**
     * UX-4 — Plan → Deudas is where debts are managed, for every plan, with the actions each plan has
     * today: Free records, pays and deletes; editing stays Basic+ (backend gate). The screen keeps
     * the Plan tab selected.
     */
    @Test fun debtsAreManagedFromPlanForEveryPlan() {
        launch(plan = "free")
        home()
        click(tx("Plan", "Plan"))
        click(tx("Deudas", "Debts"))
        waitForText("Tarjeta de ejemplo")
        // Opened from Plan, the screen keeps Plan selected.
        compose.onNode(hasText(tx("Plan", "Plan")) and isSelected()).assertExists()
        waitForText(tx("Registrar pago", "Record payment"))
        waitForText(tx("Eliminar", "Delete"))
        assertTrue("editing stays Basic+ (PUT is gated strategy_basic)", !present(tx("Editar", "Edit")))
        compose.onNode(hasContentDescription(tx("Agregar deuda", "Add debt"))).performClick()
        waitForText(tx("Nueva deuda", "New debt"))
    }

    @Test fun basicEditsItsDebtsFromPlan() {
        launch(plan = "basic")
        home()
        click(tx("Plan", "Plan"))
        click(tx("Deudas", "Debts"))
        waitForText("Tarjeta de ejemplo")
        click(tx("Editar", "Edit"))
        waitForText(tx("Editar deuda", "Edit debt"))
    }

    @Test fun vipReachesDebtsFromPlan() {
        launch(plan = "vip")
        home()
        click(tx("Plan", "Plan"))
        click(tx("Deudas", "Debts"))
        waitForText("Tarjeta de ejemplo")
    }

    @Test fun theOwnerReachesDebtsFromPlan() {
        launch(role = "owner")
        home()
        click(tx("Plan", "Plan"))
        click(tx("Deudas", "Debts"))
        waitForText("Tarjeta de ejemplo")
    }

    @Test fun aReviewInCuentasShowsInCorreosAndViceVersa() {
        launch(plan = "vip")
        home()
        // §15 PR 10: Cuentas and Correos live in Patrimonio. "Cuentas" replaces "Cuentas detectadas".
        click(tx("Patrimonio", "Wealth"))
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
        click(tx("Conexiones de correo", "Mail connections"))
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

    @Test fun profileShowsTheSubscriptionOfEachTierAndTheOwnerIsNotOne() {
        // UX-12: Free / Basic / VIP are subscriptions in Perfil → Suscripción; "Plan" is the financial plan.
        listOf("free" to tx("Gratis", "Free"), "basic" to "Basic", "vip" to "VIP").forEach { (plan, name) ->
            launch(plan = plan)
            home()
            click(tx("Perfil", "Profile"))
            click(tx("Suscripción", "Subscription"))
            waitForText(tx("Suscripción actual", "Current subscription"))
            waitForText(name)
            assertTrue("$plan: no Owner card", compose.onAllNodes(hasTestTag("subscription.owner"), useUnmergedTree = true).fetchSemanticsNodes().isEmpty())
        }
        launch(role = "owner")
        home()
        click(tx("Perfil", "Profile"))
        click(tx("Suscripción", "Subscription"))
        waitForTag("subscription.owner")
        assertTrue("no tier for the Owner", !present(tx("Suscripción actual", "Current subscription")))
        assertTrue("nothing to choose", !present(tx("Cambiar a", "Switch to"), substring = true))
    }

    @Test fun tuPlanDelMesStaysTheFinancialPlan() {
        launch(plan = "basic")
        home()
        click(tx("Plan", "Plan"))
        click(tx("Tu plan del mes", "Your plan for the month"))
        waitForText(tx("Libre después de tus compromisos", "Left after your commitments"))
        assertTrue("the financial plan is not the subscription", !present(tx("Suscripción actual", "Current subscription")))
    }

    @Test fun freeCreatesEditsAndDeletesRecurringCommitments() {
        // UX-9: registering fixed/recurring commitments is every plan's; budget and calendar stay Basic.
        launch(plan = "free")
        home()
        click(tx("Perfil", "Profile"))
        // PR 4: budget and calendar stay Basic, shown locked.
        waitForText(tx("Calendario financiero", "Financial calendar"))
        assertTrue("budget and calendar locked", present(tx("Disponible desde Basic", "Available from Basic")))
        click(tx("Movimientos recurrentes", "Recurring transactions"))
        waitForText(tx("Gastos fijos por mes", "Fixed expenses per month"))
        // Create.
        compose.onNodeWithContentDescription(tx("Agregar recurrente", "Add recurring")).performClick()
        compose.onAllNodes(hasText(tx("Nombre", "Name"))).onFirst().performTextInput("Gimnasio sintético")
        compose.onAllNodes(hasText(tx("Monto", "Amount"))).onFirst().performTextInput("15000")
        click(tx("Guardar", "Save"))
        waitForText("Gimnasio sintético")
        // Edit (every field, through the same form).
        click(tx("Editar", "Edit"))
        waitForText(tx("Editar pago recurrente", "Edit recurring payment"))
        compose.onAllNodes(hasText(tx("Nombre", "Name"))).onFirst().performTextClearance()
        compose.onAllNodes(hasText(tx("Nombre", "Name"))).onFirst().performTextInput("Editado sintético")
        click(tx("Guardar", "Save"))
        waitForText("Editado sintético")
        // Delete.
        click(tx("Eliminar", "Delete"))
        compose.onAllNodes(hasText(tx("Eliminar", "Delete")) and hasClickAction()).onLast().performSemanticsAction(SemanticsActions.OnClick)
        waitForGone("Editado sintético")
    }

    @Test fun onboardingShowsTheBankLogosAndSaysItConnectsNothing() {
        launch(fixture = "NEW_USER")
        waitForTag("setup.continue")
        tapTag("setup.continue")
        // The goal is the last-but-one option: on a small screen (CI's API 24 is 320×640) it sits at the
        // bottom edge, where a tap at its center misses it. click() invokes the row's own action.
        click(tx("Tomar control de mis finanzas", "Take control of my finances"))
        tapTag("setup.continue")
        tapTag("setup.continue")
        waitForText(tx("Esta selección no conecta tus cuentas", "This selection does not connect your accounts"), substring = true)
        listOf("bac", "bn", "bcr", "popular", "davivienda", "davibank", "promerica", "multimoney").forEach { waitForTag("bank.logo.$it") }
        tapTag("setup.bank.bac")
        tapTag("setup.continue")
        waitForText(tx("Elegí tu suscripción", "Choose your subscription"))
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
        waitForText(tx("Ajustes de cuenta", "Account settings"))
        assertTrue(!present("JARVIS") && !present(tx("Análisis financiero", "Financial analysis")))
        launch(plan = "vip", role = "admin")
        waitForText(tx("Esta cuenta no está disponible en DINCR", "This account isn’t available in DINCR"))
        assertTrue(!present(tx("Análisis financiero", "Financial analysis")))
    }

    @Test fun ingresosYBaseSendsWorkDaysForAFixedIncome() {
        // UX-7: the declared income lives in Plan → Ingresos y base.
        launch(plan = "free")
        home()
        click(tx("Plan", "Plan"))
        click(tx("Ingresos y base", "Income and base"))
        waitForTag("incomeBase.days")
        compose.onNodeWithTag("incomeBase.days").assert(hasText("5"))
        compose.onAllNodes(hasText(tx("Salario mensual", "Monthly salary"))).onFirst().performTextInput("800.000")
        click(tx("Guardar", "Save"))
        // The fake answers 422 without work_days_per_week, like the backend: the saved salary is
        // what the server returns when the screen is opened again.
        repeat(20) { advance(); Thread.sleep(100) } // the in-memory server answers in milliseconds
        back()
        click(tx("Ingresos y base", "Income and base"))
        waitUntil("the stored salary") { present("800.000") }
        compose.onNodeWithTag("incomeBase.days").assert(hasText("5"))
    }

    @Test fun freeKeepsEveryDeclaredFigureInItsHomeAndPerfilHasNoSituacion() {
        // UX-7: income and essential expenses in Plan → Ingresos y base; savings in Metas y ahorros.
        launch(plan = "free")
        home()
        click(tx("Plan", "Plan"))
        click(tx("Ingresos y base", "Income and base"))
        waitForTag("incomeBase.days")
        scrollTo(tx("Gastos esenciales del mes", "Essential monthly expenses"))
        assertTrue("savings live in Ahorros", !present(tx("Ahorros disponibles", "Available savings")))
        back()
        click(tx("Hoy", "Today"))
        click(tx("Metas y ahorros", "Goals and savings"))
        click(tx("Tus ahorros", "Your savings"))
        waitForText(tx("Ahorros disponibles", "Available savings"))
        scrollTo(tx("Meta de fondo de emergencia", "Emergency fund target"))
        back(); back()
        click(tx("Perfil", "Profile"))
        waitForText(tx("Ajustes de cuenta", "Account settings"))
        assertTrue("no Situación row in Perfil", !present(tx("Mi situación financiera", "My financial situation")))
    }

    @Test fun vipSeesDincrsRecommendationAndSetsOnlyTheMinimum() {
        launch(plan = "vip")
        home()
        click(tx("Plan", "Plan"))
        click(tx("Tu plan del mes", "Your plan for the month"))
        click(tx("Ajustes del plan", "Plan settings"))
        // The settings are saved with the declared profile: without an income they say where to declare it.
        waitForText(tx("Primero declará tu ingreso: tus ajustes se guardan junto con él.", "Declare your income first: your settings are saved with it."))
        assertTrue("no save without a declared income", !present(tx("Guardar", "Save")))
        back(); back()
        click(tx("Ingresos y base", "Income and base"))
        waitForTag("incomeBase.days")
        compose.onAllNodes(hasText(tx("Salario mensual", "Monthly salary"))).onFirst().performTextInput("800.000")
        click(tx("Guardar", "Save"))
        waitForText(tx("Ingresos y base guardados", "Income and base saved"))
        back()
        click(tx("Tu plan del mes", "Your plan for the month"))
        // UX-8: DINCR's recommendation is shown, and the priority is not a free choice in the settings.
        waitForText(tx("Recomendación de DINCR", "DINCR’s recommendation"))
        click(tx("Ajustes del plan", "Plan settings"))
        waitForText(tx("Mínimo personal por mes", "Personal minimum per month"))
        assertTrue("no priority picker", !present(tx("Sin preferencia", "No preference")) && !present(tx("Equilibrado", "Balanced")))
        click(tx("Guardar", "Save"))
        waitForText(tx("Ajustes guardados", "Settings saved"))
        launch(plan = "basic")
        home()
        click(tx("Plan", "Plan"))
        click(tx("Tu plan del mes", "Your plan for the month"))
        waitForText(tx("Libre después de tus compromisos", "Left after your commitments"))
        waitForText(tx("Recomendación de DINCR", "DINCR’s recommendation"))
        assertTrue("the settings are VIP", !present(tx("Ajustes del plan", "Plan settings")))
    }

    @Test fun basicHomeOpensMovementsWhichShowTheOriginalCurrency() {
        launch(plan = "basic")
        waitForText(tx("Resultado del mes", "This month’s result"))
        // UX-6: the month's history chart left Hoy (it lives in Resumen del mes / Movimientos).
        click(tx("Movimientos", "Transactions"))
        // The rate follows the app language's decimal separator (507,5 / 507.5): match what both share.
        waitForText(tx("TC 507", "Rate 507"), substring = true)
    }
}
