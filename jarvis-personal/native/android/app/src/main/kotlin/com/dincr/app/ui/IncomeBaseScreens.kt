package com.dincr.app.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.KeyboardType
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AmountInput
import com.dincr.data.AuthException
import com.dincr.data.FinancialProfile
import com.dincr.data.FinancialSituation
import com.dincr.data.IdempotencyKey
import com.dincr.data.SituationDefaults
import com.dincr.data.StrategyPreference
import com.dincr.data.WholeNumberInput
import com.dincr.design.Dincr
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.ErrorState
import kotlinx.coroutines.launch

/**
 * UX-7 — Plan → Ingresos y base: the declared income and essential expenses, for every plan (with
 * Metas y ahorros → Tus ahorros and Tu plan del mes → Ajustes it replaces the Situación screen;
 * same source, `financial_profiles`, and the same endpoint). Empty means unknown (null), never zero;
 * the observed income average is a hint only and is never copied into the declared salary. Saving
 * keeps the fields edited elsewhere exactly as stored. iOS twin: `IncomeBaseView`.
 */
@Composable
fun IncomeBaseScreen(model: AppModel, nav: Navigator) {
    val situation = rememberLoad(model) { model.api.financialSituation() }
    DetailScaffold(tx("Ingresos y base", "Income and base"), nav::back) {
        LoadContent(situation) { s -> IncomeBaseForm(model, s.profile, s.observed?.monthlyIncomeAverage) { situation.replace(it) } }
    }
}

@Composable
private fun IncomeBaseForm(model: AppModel, current: FinancialProfile?, observedIncome: java.math.BigDecimal?, onSaved: (FinancialSituation) -> Unit) {
    val format = Dincr.money
    fun text(value: java.math.BigDecimal?) = value?.let(format::inputText).orEmpty()
    var incomeType by remember { mutableStateOf(current?.incomeType ?: "fixed") }
    var salary by remember { mutableStateOf(text(current?.fixedMonthlySalary)) }
    var hourly by remember { mutableStateOf(text(current?.hourlyRate)) }
    // Every income type needs work_days_per_week (1–7, NOT NULL): prefilled, or 5 like the web form.
    var days by remember { mutableStateOf(SituationDefaults.workDays(current).toString()) }
    var hours by remember { mutableStateOf(current?.hoursPerDay?.let(format::inputText).orEmpty()) }
    var frequency by remember { mutableStateOf(current?.payFrequency ?: "monthly") }
    var essentials by remember { mutableStateOf(text(current?.essentialMonthlyExpenses)) }
    var errors by remember { mutableStateOf(mapOf<String, String>()) }
    var error by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    Section(tx("Tus ingresos", "Your income")) {
        observedIncome?.takeIf { it.signum() > 0 }?.let { Caption(tx("En los últimos 90 días registraste en promedio ${format.format(it)} por mes.", "In the last 90 days you recorded ${format.format(it)} per month on average.")) }
        ChoiceChips(listOf("fixed" to tx("Salario fijo", "Fixed salary"), "hourly" to tx("Por horas", "Hourly")), incomeType, { incomeType = it })
        if (incomeType == "fixed") MoneyField(tx("Salario mensual", "Monthly salary"), salary, { salary = it }, errors["salary"])
        else MoneyField(tx("Pago por hora", "Hourly rate"), hourly, { hourly = it }, errors["hourly"])
        FormField(tx("Días que trabajás por semana", "Days you work per week"), days, { days = it }, errors["days"], KeyboardType.Number,
            supporting = tx("Entre 1 y 7.", "1 to 7."), modifier = Modifier.testTag("incomeBase.days"))
        if (incomeType == "hourly") FormField(tx("Horas por día", "Hours per day"), hours, { hours = it }, errors["hours"], KeyboardType.Decimal)
        ChoiceChips(listOf("weekly" to tx("Semanal", "Weekly"), "biweekly" to tx("Quincenal", "Every two weeks"), "monthly" to tx("Mensual", "Monthly")), frequency, { frequency = it }, tx("Te pagan", "You get paid"))
    }
    Section(tx("Gastos esenciales", "Essential expenses")) {
        MoneyField(tx("Gastos esenciales del mes", "Essential monthly expenses"), essentials, { essentials = it }, errors["essentials"])
        Caption(tx("Dejá vacío lo que no sabés: DINCR lo trata como desconocido, no como cero.", "Leave empty what you don’t know: DINCR treats it as unknown, not zero."))
    }
    error?.let { ErrorState(it) }
    DincrPrimaryButton(tx("Guardar", "Save"), loading = saving, onClick = {
        val found = mutableMapOf<String, String>()
        fun money(key: String, value: String, positive: Boolean = false) = if (value.isBlank()) null else
            (if (positive) AmountInput.parse(value, format.separators) else AmountInput.parseZeroOrMore(value, format.separators)).also { if (it == null) found[key] = tx("Monto no válido.", "Not a valid amount.") }
        val request = (current ?: FinancialProfile()).copy(
            incomeType = incomeType,
            fixedMonthlySalary = if (incomeType == "fixed") money("salary", salary, positive = true) else null,
            hourlyRate = if (incomeType == "hourly") money("hourly", hourly, positive = true) else null,
            // Always sent, for every income type (the backend answers 422 without it).
            workDaysPerWeek = WholeNumberInput.parse(days, SituationDefaults.WORK_DAYS_RANGE).also { if (it == null) found["days"] = tx("Entre 1 y 7.", "1 to 7.") },
            hoursPerDay = if (incomeType == "hourly" && hours.isNotBlank()) AmountInput.parseDecimal(hours, format.separators, 2, java.math.BigDecimal(24), allowZero = false).also { if (it == null) found["hours"] = tx("Entre 0 y 24.", "0 to 24.") } else current?.hoursPerDay,
            payFrequency = frequency,
            essentialMonthlyExpenses = money("essentials", essentials),
        )
        errors = found
        if (found.isNotEmpty()) return@DincrPrimaryButton
        saving = true; error = null
        val key = IdempotencyKey.new()
        scope.launch {
            model.load(tx("No pudimos guardar tus ingresos y base.", "We couldn’t save your income and base.")) { model.api.updateFinancialSituation(request, key) }
                .onSuccess { onSaved(it); model.showNotice(tx("Ingresos y base guardados", "Income and base saved")) }
                .onFailure { if (it !is AuthException.SignedOut) error = it.message }
            saving = false
        }
    }, modifier = Modifier.testTag("incomeBase.save"))
}

/**
 * UX-7 — Tu plan del mes → Ajustes (VIP): the plan priority and the personal minimum per month,
 * moved from the Situación screen. Same source and endpoint; every other declared field is sent
 * back exactly as stored. "No preference" stays null. iOS twin: `PlanPreferencesView`.
 */
@Composable
fun PlanPreferencesScreen(model: AppModel, nav: Navigator) {
    val situation = rememberLoad(model) { model.api.financialSituation() }
    DetailScaffold(tx("Ajustes del plan", "Plan settings"), nav::back) {
        LoadContent(situation) { s -> PlanPreferencesForm(model, nav, s.profile) { situation.replace(it) } }
    }
}

@Composable
private fun PlanPreferencesForm(model: AppModel, nav: Navigator, current: FinancialProfile?, onSaved: (FinancialSituation) -> Unit) {
    val format = Dincr.money
    var preference by remember { mutableStateOf(current?.strategyPreference.orEmpty()) }
    var minimum by remember { mutableStateOf(current?.discretionaryMonthlyMinimum?.let(format::inputText).orEmpty()) }
    var minimumError by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    // The backend saves the whole declared profile, which needs a declared income: until there is one,
    // the settings say where to declare it (the old Situación form asked for it on the same page).
    val incomeDeclared = incomeDeclared(current)
    if (!incomeDeclared) DeclareIncomeFirst(tx("Primero declará tu ingreso: tus ajustes se guardan junto con él.", "Declare your income first: your settings are saved with it."), nav)
    Section(tx("Prioridad", "Priority")) {
        ChoiceChips(StrategyPreference.choices.map { (it?.code ?: "") to preferenceLabel(it) }, preference, { preference = it })
        MoneyField(tx("Mínimo personal por mes", "Personal minimum per month"), minimum, { minimum = it }, minimumError)
        Caption(tx("Dejá vacío el mínimo si no lo sabés: DINCR lo trata como desconocido, no como cero.", "Leave the minimum empty if you don’t know it: DINCR treats it as unknown, not zero."))
    }
    error?.let { ErrorState(it) }
    if (incomeDeclared) DincrPrimaryButton(tx("Guardar", "Save"), loading = saving, onClick = {
        val minimumValue = if (minimum.isBlank()) null else AmountInput.parseZeroOrMore(minimum, format.separators)
        minimumError = if (minimum.isNotBlank() && minimumValue == null) tx("Monto no válido.", "Not a valid amount.") else null
        if (minimumError != null) return@DincrPrimaryButton
        val request = withDefaults(current).copy(
            strategyPreference = preference.ifEmpty { null },
            discretionaryMonthlyMinimum = minimumValue,
        )
        saving = true; error = null
        val key = IdempotencyKey.new()
        scope.launch {
            model.load(tx("No pudimos guardar los ajustes.", "We couldn’t save the settings.")) { model.api.updateFinancialSituation(request, key) }
                .onSuccess { onSaved(it); model.showNotice(tx("Ajustes guardados", "Settings saved")) }
                .onFailure { if (it !is AuthException.SignedOut) error = it.message }
            saving = false
        }
    }, modifier = Modifier.testTag("planPreferences.save"))
}

private fun preferenceLabel(choice: StrategyPreference?): String = when (choice) {
    null -> tx("Sin preferencia", "No preference")
    StrategyPreference.DEBT -> tx("Salir de deudas", "Get out of debt")
    StrategyPreference.EMERGENCY -> tx("Fondo de emergencia", "Emergency fund")
    StrategyPreference.GOALS -> tx("Metas", "Goals")
    StrategyPreference.BALANCED -> tx("Equilibrado", "Balanced")
}

/**
 * UX-7 — Metas y ahorros → Tus ahorros: the declared available savings and the emergency-fund
 * target, for every plan (moved from the Situación screen; the same `financial_profiles` fields and
 * endpoint, the same figures Salvavidas reads). Saving needs a declared income, as before. iOS twin:
 * `DeclaredSavingsView`.
 */
@Composable
fun DeclaredSavingsScreen(model: AppModel, nav: Navigator) {
    val situation = rememberLoad(model) { model.api.financialSituation() }
    DetailScaffold(tx("Tus ahorros", "Your savings"), nav::back) {
        LoadContent(situation) { s -> DeclaredSavingsForm(model, nav, s.profile) { situation.replace(it) } }
    }
}

@Composable
private fun DeclaredSavingsForm(model: AppModel, nav: Navigator, current: FinancialProfile?, onSaved: (FinancialSituation) -> Unit) {
    val format = Dincr.money
    fun text(value: java.math.BigDecimal?) = value?.let(format::inputText).orEmpty()
    var savings by remember { mutableStateOf(text(current?.liquidSavings)) }
    var emergency by remember { mutableStateOf(text(current?.emergencyFundTarget)) }
    var errors by remember { mutableStateOf(mapOf<String, String>()) }
    var error by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val incomeDeclared = incomeDeclared(current)
    if (!incomeDeclared) DeclareIncomeFirst(tx("Primero declará tu ingreso: tus ahorros se guardan junto con él.", "Declare your income first: your savings are saved with it."), nav)
    Section(tx("Tus ahorros", "Your savings")) {
        MoneyField(tx("Ahorros disponibles", "Available savings"), savings, { savings = it }, errors["savings"])
        MoneyField(tx("Meta de fondo de emergencia", "Emergency fund target"), emergency, { emergency = it }, errors["emergency"])
        Caption(tx("Dejá vacío lo que no sabés: DINCR lo trata como desconocido, no como cero.", "Leave empty what you don’t know: DINCR treats it as unknown, not zero."))
    }
    error?.let { ErrorState(it) }
    if (incomeDeclared) DincrPrimaryButton(tx("Guardar", "Save"), loading = saving, onClick = {
        val found = mutableMapOf<String, String>()
        fun money(key: String, value: String) = if (value.isBlank()) null else
            AmountInput.parseZeroOrMore(value, format.separators).also { if (it == null) found[key] = tx("Monto no válido.", "Not a valid amount.") }
        val request = withDefaults(current).copy(liquidSavings = money("savings", savings), emergencyFundTarget = money("emergency", emergency))
        errors = found
        if (found.isNotEmpty()) return@DincrPrimaryButton
        saving = true; error = null
        val key = IdempotencyKey.new()
        scope.launch {
            model.load(tx("No pudimos guardar tus ahorros.", "We couldn’t save your savings.")) { model.api.updateFinancialSituation(request, key) }
                .onSuccess { onSaved(it); model.showNotice(tx("Ahorros guardados", "Savings saved")) }
                .onFailure { if (it !is AuthException.SignedOut) error = it.message }
            saving = false
        }
    }, modifier = Modifier.testTag("declaredSavings.save"))
}

/** Whether the stored profile has the income the backend requires to save it. */
private fun incomeDeclared(current: FinancialProfile?): Boolean = when (current?.incomeType) {
    "fixed" -> current.fixedMonthlySalary != null
    "hourly" -> current.hourlyRate != null && current.hoursPerDay != null
    else -> false
}

/** The stored profile with the same defaults the old Situación form sent for what was never stored. */
private fun withDefaults(current: FinancialProfile?): FinancialProfile =
    (current ?: FinancialProfile()).copy(workDaysPerWeek = SituationDefaults.workDays(current), payFrequency = current?.payFrequency ?: "monthly")

@Composable
private fun DeclareIncomeFirst(message: String, nav: Navigator) {
    Section(tx("Primero tu ingreso", "Your income first")) {
        Caption(message)
        DincrPrimaryButton(tx("Completar ingresos y base", "Complete income and base"), { nav.open("incomeBase") })
    }
}
