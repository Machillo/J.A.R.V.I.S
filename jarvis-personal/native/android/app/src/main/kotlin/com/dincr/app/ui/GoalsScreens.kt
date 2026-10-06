package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Payments
import androidx.compose.ui.platform.testTag
import androidx.compose.foundation.layout.Box
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Flag
import androidx.compose.material.icons.rounded.Savings
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AmountInput
import com.dincr.data.ApiError
import com.dincr.data.AuthException
import com.dincr.data.Feature
import com.dincr.data.Goal
import com.dincr.data.GoalContribution
import com.dincr.data.GoalRequest
import com.dincr.data.IdempotencyKey
import com.dincr.data.PlanTier
import com.dincr.data.SavingsContribution
import com.dincr.data.SavingsPlan
import com.dincr.data.SavingsPlanRequest
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.EmptyState
import com.dincr.design.MoneyText
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal
import java.time.LocalDate
import kotlinx.coroutines.launch

private data class GoalsData(val goals: List<Goal>, val plans: List<SavingsPlan>)

/** E6/E7 — goals and savings plans for every plan (edits need Basic, as the backend requires). */
@Composable
fun GoalsScreen(model: AppModel, nav: Navigator) {
    val profile by model.profile.collectAsStateWithLifecycle()
    val advanced = (profile?.planTier ?: PlanTier.FREE).allows(Feature.STRATEGY_BASIC)
    val data = rememberLoad(model) { GoalsData(model.api.goals(), model.api.savingsPlans()) }
    var goalForm by remember { mutableStateOf<Goal?>(null) }
    var creatingGoal by remember { mutableStateOf(false) }
    var planForm by remember { mutableStateOf<SavingsPlan?>(null) }
    var creatingPlan by remember { mutableStateOf(false) }
    var contributeGoal by remember { mutableStateOf<Goal?>(null) }
    var contributePlan by remember { mutableStateOf<SavingsPlan?>(null) }
    var confirm by remember { mutableStateOf<Pair<String, suspend () -> Unit>?>(null) }
    var busy by remember { mutableStateOf(false) }
    var menu by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) { model.recordScreen("goals_opened", "goals") }
    DetailScaffold(tx("Metas y ahorros", "Goals and savings"), nav::back, actions = {
        IconButton({ menu = true }, modifier = Modifier.heightIn(min = 48.dp)) { Icon(Icons.Rounded.Add, contentDescription = tx("Agregar", "Add")) }
        DropdownMenu(menu, { menu = false }) {
            DropdownMenuItem({ Text(tx("Nueva meta", "New goal")) }, { menu = false; creatingGoal = true })
            DropdownMenuItem({ Text(tx("Nuevo plan de ahorro", "New savings plan")) }, { menu = false; creatingPlan = true })
        }
    }) {
        // UX-7: the declared available savings and emergency-fund target (moved from Situación).
        Box(Modifier.testTag("goals.declaredSavings")) {
            DincrCard { NavRow(Icons.Rounded.Payments, tx("Tus ahorros", "Your savings"), tx("Ahorros disponibles y meta de fondo de emergencia", "Available savings and emergency fund target")) { nav.open("declaredSavings") } }
        }
        LoadContent(data) { (goals, plans) ->
            SectionTitle(tx("Metas", "Goals"))
            if (goals.isEmpty()) EmptyState(Icons.Rounded.Flag, tx("Todavía no tenés metas", "No goals yet"), tx("Definí para qué estás ahorrando y cuánto necesitás.", "Set what you’re saving for and how much you need.")) {
                DincrPrimaryButton(tx("Crear meta", "Create goal"), { creatingGoal = true })
            }
            if (goals.isNotEmpty()) {
                val current = goals.sumOf { it.currentAmount ?: BigDecimal.ZERO }
                val target = goals.sumOf { it.targetAmount ?: BigDecimal.ZERO }
                percentOf(current, target)?.let { ProgressLine(it, tx("${(it * 100).toInt()} % del total de tus metas", "${(it * 100).toInt()} % of all your goals")) }
            }
            goals.forEach { goal ->
                DincrCard {
                    Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(goal.name.orEmpty(), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
                                Caption(listOfNotNull(priorityLabel(goal.priority), statusLabel(goal.status), goal.targetDate?.let { tx("Para el ", "By ") + dateLabel(it) }).joinToString(" · "))
                            }
                            MoneyText(goal.targetAmount)
                        }
                        percentOf(goal.currentAmount, goal.targetAmount)?.let { ProgressLine(it, tx("${Dincr.money.format(goal.currentAmount ?: BigDecimal.ZERO)} ahorrados", "${Dincr.money.format(goal.currentAmount ?: BigDecimal.ZERO)} saved")) }
                        monthlyNeeded(goal)?.let { AmountLine(tx("Necesitás por mes", "You need each month"), it) }
                        Row {
                            if (goal.status != "completed" && (goal.currentAmount ?: BigDecimal.ZERO) < (goal.targetAmount ?: BigDecimal.ZERO)) TextButton({ contributeGoal = goal }, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Aportar", "Contribute"), color = Dincr.colors.tint) }
                            if (advanced) TextButton({ goalForm = goal }, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Editar", "Edit"), color = Dincr.colors.tint) }
                            TextButton({ confirm = goal.name.orEmpty() to { model.api.deleteGoal(goal.id) } }, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Eliminar", "Delete"), color = Dincr.colors.negative) }
                        }
                    }
                }
            }
            SectionTitle(tx("Planes de ahorro", "Savings plans"))
            if (plans.isEmpty()) EmptyState(Icons.Rounded.Savings, tx("Sin planes de ahorro", "No savings plans"), tx("Apartá un monto fijo cada mes hasta una fecha.", "Set aside a fixed amount every month until a date.")) {
                DincrPrimaryButton(tx("Crear plan", "Create plan"), { creatingPlan = true })
            }
            plans.forEach { plan ->
                DincrCard {
                    Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(plan.name.orEmpty(), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
                                Caption(listOfNotNull(statusLabel(plan.status), "${dateLabel(plan.startDate)} – ${dateLabel(plan.endDate)}").joinToString(" · "))
                            }
                            MoneyText(plan.savedAmount)
                        }
                        AmountLine(tx("Aporte mensual", "Monthly amount"), plan.monthlyAmount)
                        Row {
                            if (plan.status != "completed") TextButton({ contributePlan = plan }, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Aportar", "Contribute"), color = Dincr.colors.tint) }
                            TextButton({ planForm = plan }, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Editar", "Edit"), color = Dincr.colors.tint) }
                            TextButton({ confirm = plan.name.orEmpty() to { model.api.deleteSavingsPlan(plan.id) } }, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Eliminar", "Delete"), color = Dincr.colors.negative) }
                        }
                    }
                }
            }
        }
    }
    if (creatingGoal || goalForm != null) GoalForm(model, goalForm, onDismiss = { creatingGoal = false; goalForm = null }) { creatingGoal = false; goalForm = null; data.reload(); model.showNotice(it) }
    if (creatingPlan || planForm != null) SavingsPlanForm(model, planForm, onDismiss = { creatingPlan = false; planForm = null }) { creatingPlan = false; planForm = null; data.reload(); model.showNotice(it) }
    contributeGoal?.let { goal ->
        AmountDialog(tx("Aportar a «${goal.name.orEmpty()}»", "Contribute to “${goal.name.orEmpty()}”"),
            tx("Faltan ${Dincr.money.format(((goal.targetAmount ?: BigDecimal.ZERO) - (goal.currentAmount ?: BigDecimal.ZERO)).max(BigDecimal.ZERO))}. Un aporte mayor se ajusta a la meta.", "${Dincr.money.format(((goal.targetAmount ?: BigDecimal.ZERO) - (goal.currentAmount ?: BigDecimal.ZERO)).max(BigDecimal.ZERO))} to go. A larger amount is capped at the goal."),
            tx("Aportar", "Contribute"), onDismiss = { contributeGoal = null }) { amount, key ->
            model.load(tx("No pudimos registrar el aporte.", "We couldn’t record the contribution.")) { model.api.contributeToGoal(goal.id, GoalContribution(amount, LocalDate.now().toString()), key) }
                .fold({ contributeGoal = null; data.reload(); model.showNotice(tx("Aporte registrado", "Contribution recorded")); null }, { if (it is AuthException.SignedOut) null else it.message })
        }
    }
    contributePlan?.let { plan ->
        AmountDialog(tx("Aportar a «${plan.name.orEmpty()}»", "Contribute to “${plan.name.orEmpty()}”"), null, tx("Aportar", "Contribute"), onDismiss = { contributePlan = null }) { amount, key ->
            model.load(tx("No pudimos registrar el aporte.", "We couldn’t record the contribution.")) { model.api.contributeToSavingsPlan(plan.id, SavingsContribution(amount, LocalDate.now().toString()), key) }
                .fold({ contributePlan = null; data.reload(); model.showNotice(tx("Aporte registrado", "Contribution recorded")); null }, { if (it is AuthException.SignedOut) null else it.message })
        }
    }
    confirm?.let { (name, action) ->
        ConfirmDialog(tx("¿Eliminar «$name»?", "Delete “$name”?"), tx("No se puede deshacer.", "This can’t be undone."), tx("Eliminar", "Delete"), busy = busy, onDismiss = { confirm = null }, onConfirm = {
            busy = true
            scope.launch {
                val result = model.load(tx("No pudimos eliminarlo.", "We couldn’t delete it.")) { action() }
                busy = false; confirm = null
                if (result.isSuccess || (result.exceptionOrNull() as? ApiError)?.kind == ApiError.Kind.NOT_FOUND) data.reload()
                else result.exceptionOrNull()?.takeIf { it !is AuthException.SignedOut }?.message?.let(model::showNotice)
            }
        })
    }
}

fun priorityLabel(priority: String?) = when (priority) {
    "critical" -> tx("Prioridad crítica", "Critical priority")
    "high" -> tx("Prioridad alta", "High priority")
    "low" -> tx("Prioridad baja", "Low priority")
    else -> tx("Prioridad media", "Medium priority")
}

fun statusLabel(status: String?) = when (status) {
    "paused" -> tx("En pausa", "Paused")
    "completed" -> tx("Completada", "Completed")
    else -> null
}

/** Presentation only: what is left over the months to the target date (at least one). */
private fun monthlyNeeded(goal: Goal): BigDecimal? {
    val date = goal.targetDate?.let { runCatching { LocalDate.parse(it.take(10)) }.getOrNull() } ?: return null
    val remaining = (goal.targetAmount ?: return null) - (goal.currentAmount ?: BigDecimal.ZERO)
    if (remaining.signum() <= 0) return null
    val months = java.time.temporal.ChronoUnit.MONTHS.between(LocalDate.now().withDayOfMonth(1), date.withDayOfMonth(1)).coerceAtLeast(1)
    return remaining.divide(BigDecimal(months), 2, java.math.RoundingMode.HALF_UP)
}

@Composable
private fun GoalForm(model: AppModel, goal: Goal?, onDismiss: () -> Unit, onSaved: (String) -> Unit) {
    val format = Dincr.money
    var name by remember { mutableStateOf(goal?.name.orEmpty()) }
    var target by remember { mutableStateOf(goal?.targetAmount?.let(format::inputText).orEmpty()) }
    var current by remember { mutableStateOf(goal?.currentAmount?.let(format::inputText) ?: "") }
    var date by remember { mutableStateOf(goal?.targetDate?.let { runCatching { LocalDate.parse(it.take(10)) }.getOrNull() }) }
    var priority by remember { mutableStateOf(goal?.priority?.takeIf { it in com.dincr.data.GOAL_PRIORITIES } ?: "medium") }
    var status by remember { mutableStateOf(goal?.status ?: "active") }
    var errors by remember { mutableStateOf(mapOf<String, String>()) }
    var error by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    val key = remember { IdempotencyKey.new() }
    val scope = rememberCoroutineScope()
    FormSheet(if (goal == null) tx("Nueva meta", "New goal") else tx("Editar meta", "Edit goal"), saving, error, tx("Guardar", "Save"), onDismiss = onDismiss, onPrimary = {
        val found = mutableMapOf<String, String>()
        if (name.isBlank()) found["name"] = tx("Escribí un nombre.", "Enter a name.")
        val targetValue = AmountInput.parse(target, format.separators).also { if (it == null) found["target"] = tx("Escribí el monto objetivo.", "Enter the target amount.") }
        val currentValue = if (current.isBlank()) BigDecimal.ZERO else AmountInput.parseZeroOrMore(current, format.separators).also { if (it == null) found["current"] = tx("Monto no válido.", "Not a valid amount.") }
        errors = found
        if (found.isNotEmpty() || targetValue == null || currentValue == null) return@FormSheet
        saving = true; error = null
        val request = GoalRequest(name.trim(), targetValue, currentValue, date?.toString(), priority, if (goal == null) null else status)
        scope.launch {
            model.load(tx("No pudimos guardar la meta.", "We couldn’t save the goal.")) {
                if (goal == null) model.api.createGoal(request, key) else model.api.updateGoal(goal.id, request, key)
            }.onSuccess { onSaved(if (goal == null) tx("Meta creada", "Goal created") else tx("Meta actualizada", "Goal updated")) }
                .onFailure { if (it !is AuthException.SignedOut) error = it.message }
            saving = false
        }
    }) {
        FormField(tx("Nombre", "Name"), name, { name = it }, errors["name"])
        MoneyField(tx("Monto objetivo", "Target amount"), target, { target = it }, errors["target"])
        MoneyField(tx("Ya ahorrado", "Already saved"), current, { current = it }, errors["current"])
        DateField(tx("Fecha objetivo (opcional)", "Target date (optional)"), date, { date = it }, allowClear = true)
        ChoiceChips(listOf("low" to tx("Baja", "Low"), "medium" to tx("Media", "Medium"), "high" to tx("Alta", "High"), "critical" to tx("Crítica", "Critical")), priority, { priority = it }, tx("Prioridad", "Priority"))
        if (goal != null) ChoiceChips(listOf("active" to tx("Activa", "Active"), "paused" to tx("En pausa", "Paused"), "completed" to tx("Completada", "Completed")), status, { status = it }, tx("Estado", "Status"))
    }
}

@Composable
private fun SavingsPlanForm(model: AppModel, plan: SavingsPlan?, onDismiss: () -> Unit, onSaved: (String) -> Unit) {
    val format = Dincr.money
    var name by remember { mutableStateOf(plan?.name.orEmpty()) }
    var monthly by remember { mutableStateOf(plan?.monthlyAmount?.let(format::inputText).orEmpty()) }
    var saved by remember { mutableStateOf(plan?.savedAmount?.let(format::inputText) ?: "") }
    var start by remember { mutableStateOf(plan?.startDate?.let { runCatching { LocalDate.parse(it) }.getOrNull() } ?: LocalDate.now().withDayOfMonth(1)) }
    var end by remember { mutableStateOf(plan?.endDate?.let { runCatching { LocalDate.parse(it) }.getOrNull() } ?: LocalDate.now().plusMonths(12).withDayOfMonth(1)) }
    var status by remember { mutableStateOf(plan?.status ?: "active") }
    var errors by remember { mutableStateOf(mapOf<String, String>()) }
    var error by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    val key = remember { IdempotencyKey.new() }
    val scope = rememberCoroutineScope()
    FormSheet(if (plan == null) tx("Nuevo plan de ahorro", "New savings plan") else tx("Editar plan", "Edit plan"), saving, error, tx("Guardar", "Save"), onDismiss = onDismiss, onPrimary = {
        val found = mutableMapOf<String, String>()
        if (name.isBlank()) found["name"] = tx("Escribí un nombre.", "Enter a name.")
        val monthlyValue = AmountInput.parse(monthly, format.separators).also { if (it == null) found["monthly"] = tx("Escribí el aporte mensual.", "Enter the monthly amount.") }
        val savedValue = if (saved.isBlank()) BigDecimal.ZERO else AmountInput.parseZeroOrMore(saved, format.separators).also { if (it == null) found["saved"] = tx("Monto no válido.", "Not a valid amount.") }
        if (end.isBefore(start)) found["end"] = tx("La fecha final debe ser posterior al inicio.", "The end must be after the start.")
        errors = found
        if (found.isNotEmpty() || monthlyValue == null || savedValue == null) return@FormSheet
        saving = true; error = null
        val request = SavingsPlanRequest(name.trim(), monthlyValue, savedValue, start.toString(), end.toString(), if (plan == null) null else status)
        scope.launch {
            model.load(tx("No pudimos guardar el plan.", "We couldn’t save the plan.")) {
                if (plan == null) model.api.createSavingsPlan(request, key) else model.api.updateSavingsPlan(plan.id, request, key)
            }.onSuccess { onSaved(if (plan == null) tx("Plan creado", "Plan created") else tx("Plan actualizado", "Plan updated")) }
                .onFailure { if (it !is AuthException.SignedOut) error = it.message }
            saving = false
        }
    }) {
        FormField(tx("Nombre", "Name"), name, { name = it }, errors["name"])
        MoneyField(tx("Aporte mensual", "Monthly amount"), monthly, { monthly = it }, errors["monthly"])
        MoneyField(tx("Ya ahorrado", "Already saved"), saved, { saved = it }, errors["saved"])
        DateField(tx("Inicio", "Start"), start, { it?.let { start = it } })
        DateField(tx("Final", "End"), end, { it?.let { end = it } })
        errors["end"]?.let { Text(it, color = Dincr.colors.negative, style = MaterialTheme.typography.bodySmall) }
        if (plan != null) ChoiceChips(listOf("active" to tx("Activo", "Active"), "paused" to tx("En pausa", "Paused"), "completed" to tx("Completado", "Completed")), status, { status = it }, tx("Estado", "Status"))
    }
}
