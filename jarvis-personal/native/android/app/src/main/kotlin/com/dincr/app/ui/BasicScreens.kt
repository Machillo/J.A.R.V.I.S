package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.rounded.KeyboardArrowRight
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.CalendarMonth
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material.icons.rounded.Repeat
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AmountInput
import com.dincr.data.ApiError
import com.dincr.data.AuthException
import com.dincr.data.BudgetLimit
import com.dincr.data.BudgetUpdate
import com.dincr.data.IdempotencyKey
import com.dincr.data.OpsFlag
import com.dincr.data.RecurringItem
import com.dincr.data.RecurringRequest
import com.dincr.data.WholeNumberInput
import com.dincr.design.CategoryBars
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.EmptyState
import com.dincr.design.MoneyText
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal
import java.time.YearMonth
import kotlinx.coroutines.launch

/** Month picker row: previous, label, next (not past the current month). */
@Composable
fun MonthPicker(month: YearMonth, onChange: (YearMonth) -> Unit, allowFuture: Boolean = false) {
    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
        IconButton({ onChange(month.minusMonths(1)) }, modifier = Modifier.heightIn(min = 48.dp)) { Icon(Icons.AutoMirrored.Rounded.KeyboardArrowLeft, contentDescription = tx("Mes anterior", "Previous month")) }
        Text(monthLabel(month), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text, modifier = Modifier.weight(1f), textAlign = androidx.compose.ui.text.style.TextAlign.Center)
        val canForward = allowFuture || month < YearMonth.now()
        IconButton({ if (canForward) onChange(month.plusMonths(1)) }, enabled = canForward, modifier = Modifier.heightIn(min = 48.dp)) { Icon(Icons.AutoMirrored.Rounded.KeyboardArrowRight, contentDescription = tx("Mes siguiente", "Next month")) }
    }
}

fun monthLabel(month: YearMonth): String =
    month.format(java.time.format.DateTimeFormatter.ofPattern(tx("MMMM yyyy", "MMMM yyyy"), if (tx("es", "en") == "es") java.util.Locale.forLanguageTag("es-CR") else java.util.Locale.US)).replaceFirstChar { it.uppercase() }

/** D7 — monthly summary (all plans). */
@Composable
fun MonthlySummaryScreen(model: AppModel, nav: Navigator) {
    var month by remember { mutableStateOf(YearMonth.now()) }
    val summary = rememberLoad(model, month) { model.api.monthlySummary(month.toString()) }
    DetailScaffold(tx("Resumen del mes", "Monthly summary"), nav::back) {
        MonthPicker(month, { month = it })
        LoadContent(summary) { s ->
            DincrCard {
                Column {
                    AmountLine(tx("Ingresos", "Income"), s.income, sign = com.dincr.data.MoneyFormat.Sign.INCOME)
                    AmountLine(tx("Gastos", "Expenses"), s.expenses)
                    AmountLine(tx("Pagos de deuda", "Debt payments"), s.debtPaid)
                    AmountLine(tx("Balance", "Balance"), s.balance, emphasize = true)
                    AmountLine(tx("Ahorros", "Savings"), s.savings)
                    s.goals?.progress?.let { ProgressLine(it / 100.0, tx("Metas: ${it.toInt()} %", "Goals: ${it.toInt()} %")) }
                }
            }
            s.topCategory?.let { top -> Section(tx("Donde más gastaste", "Where you spent most")) { AmountLine(top.category ?: tx("Sin categoría", "Uncategorized"), top.amount) } }
            if (s.categories.isNotEmpty()) Section(tx("Distribución", "Distribution")) {
                CategoryBars(s.categories.map { (it.category ?: tx("Sin categoría", "Uncategorized")) to (it.amount ?: BigDecimal.ZERO) })
            }
        }
    }
}

/** E8 — budget: limits by category (Basic). Saving replaces the whole list, as the backend does. */
@Composable
fun BudgetScreen(model: AppModel, nav: Navigator) {
    val budget = rememberLoad(model) { model.api.budget() }
    var editing by remember { mutableStateOf(false) }
    val rows = remember { mutableStateListOf<Pair<String, String>>() }
    var newCategory by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val format = Dincr.money
    LaunchedEffect(Unit) { model.recordScreen("budget_opened", "budget") }
    DetailScaffold(tx("Presupuesto", "Budget"), nav::back, actions = {
        if (!editing && budget.state is Load.Ready) TextButton({
            rows.clear(); (budget.state as Load.Ready).value.items.forEach { rows += it.category to (it.monthlyLimit?.let(format::inputText) ?: "") }
            editing = true; error = null
        }, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Editar límites", "Edit limits"), color = Dincr.colors.tint) }
    }) {
        LoadContent(budget) { b ->
            if (!editing) {
                val spent = b.items.sumOf { it.spent ?: BigDecimal.ZERO }
                DincrCard {
                    Column {
                        AmountLine(tx("Gastado este mes", "Spent this month"), spent, emphasize = true)
                        AmountLine(tx("Presupuestado", "Budgeted"), b.totalBudgeted)
                        AmountLine(tx("Disponible para categorías", "Available for categories"), b.availableForCategories)
                        percentOf(spent, b.totalBudgeted)?.let { ProgressLine(it, tx("${(it * 100).toInt()} % usado", "${(it * 100).toInt()} % used")) }
                    }
                }
                if (b.items.isEmpty()) EmptyState(Icons.Rounded.CalendarMonth, tx("Sin presupuesto", "No budget"), tx("Definí cuánto querés gastar por categoría.", "Set how much you want to spend per category."))
                b.items.forEach { item ->
                    DincrCard {
                        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text(item.category, style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text, modifier = Modifier.weight(1f))
                                MoneyText(item.spent)
                            }
                            val ratio = percentOf(item.spent, item.monthlyLimit)
                            if (ratio != null) ProgressLine(ratio, if (ratio > 1) tx("Te pasaste por ${format.format((item.spent ?: BigDecimal.ZERO) - (item.monthlyLimit ?: BigDecimal.ZERO))}", "Over by ${format.format((item.spent ?: BigDecimal.ZERO) - (item.monthlyLimit ?: BigDecimal.ZERO))}")
                                else tx("Quedan ${format.format((item.monthlyLimit ?: BigDecimal.ZERO) - (item.spent ?: BigDecimal.ZERO))} de ${format.format(item.monthlyLimit ?: BigDecimal.ZERO)}", "${format.format((item.monthlyLimit ?: BigDecimal.ZERO) - (item.spent ?: BigDecimal.ZERO))} left of ${format.format(item.monthlyLimit ?: BigDecimal.ZERO)}"))
                            else Caption(tx("Sin límite definido", "No limit set"))
                        }
                    }
                }
            } else {
                Caption(tx("Un campo vacío no se guarda como cero: quitá la categoría si no la querés.", "An empty field is not saved as zero: remove the category if you don’t want it."))
                rows.forEachIndexed { index, (category, limit) ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        MoneyField(category, limit, { rows[index] = category to it }, modifier = Modifier.weight(1f))
                        IconButton({ rows.removeAt(index) }, modifier = Modifier.heightIn(min = 48.dp)) { Icon(Icons.Rounded.Close, contentDescription = tx("Quitar $category", "Remove $category")) }
                    }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    FormField(tx("Nueva categoría", "New category"), newCategory, { newCategory = it }, modifier = Modifier.weight(1f))
                    IconButton({
                        val name = newCategory.trim()
                        if (name.isNotEmpty() && rows.none { it.first.equals(name, ignoreCase = true) }) { rows += name to ""; newCategory = "" }
                    }, modifier = Modifier.heightIn(min = 48.dp)) { Icon(Icons.Rounded.Add, contentDescription = tx("Agregar categoría", "Add category")) }
                }
                error?.let { com.dincr.design.ErrorState(it) }
                DincrPrimaryButton(tx("Guardar presupuesto", "Save budget"), loading = saving, onClick = {
                    val parsed = rows.map { (category, limit) -> category to AmountInput.parseZeroOrMore(limit, format.separators) }
                    val invalid = parsed.firstOrNull { it.second == null }
                    if (invalid != null) { error = tx("Revisá el límite de «${invalid.first}».", "Check the limit for “${invalid.first}”."); return@DincrPrimaryButton }
                    saving = true; error = null
                    val update = BudgetUpdate(parsed.map { BudgetLimit(it.first, it.second!!) })
                    val key = IdempotencyKey.new()
                    scope.launch {
                        model.load(tx("No pudimos guardar el presupuesto.", "We couldn’t save the budget.")) { model.api.updateBudget(update, key) }
                            .onSuccess { budget.replace(it); editing = false; model.showNotice(tx("Presupuesto guardado", "Budget saved")) }
                            .onFailure { if (it !is AuthException.SignedOut) error = it.message }
                        saving = false
                    }
                })
                TextButton({ editing = false }, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) { Text(tx("Cancelar", "Cancel"), color = Dincr.colors.tint) }
            }
        }
    }
}

/** E9 — financial calendar (Basic). */
@Composable
fun CalendarScreen(model: AppModel, nav: Navigator) {
    var month by remember { mutableStateOf(YearMonth.now()) }
    val calendar = rememberLoad(model, month) { model.api.calendar(month.toString()) }
    LaunchedEffect(Unit) { model.recordScreen("calendar_opened", "calendar") }
    DetailScaffold(tx("Calendario financiero", "Financial calendar"), nav::back) {
        MonthPicker(month, { month = it }, allowFuture = true)
        LoadContent(calendar) { c ->
            c.summary?.let { s ->
                DincrCard { Column { AmountLine(tx("Pagos conocidos", "Known payments"), s.payments); InfoLine(tx("Compromisos", "Commitments"), (s.commitments ?: 0).toString()) } }
            }
            if (c.events.isEmpty()) EmptyState(Icons.Rounded.CalendarMonth, tx("Nada programado", "Nothing scheduled"), tx("Tus pagos recurrentes, cuotas y metas aparecen acá.", "Your recurring payments, instalments and goals appear here."))
            c.events.groupBy { it.date.orEmpty() }.toSortedMap().forEach { (date, events) ->
                SectionTitle(dateLabel(date))
                DincrCard {
                    Column {
                        events.forEach { e -> AmountLine("${eventKind(e.kind)} · ${e.name.orEmpty()}", e.amount?.takeIf { it.signum() > 0 }, sign = if (e.kind == "income") com.dincr.data.MoneyFormat.Sign.INCOME else com.dincr.data.MoneyFormat.Sign.NONE) }
                    }
                }
            }
        }
    }
}

private fun eventKind(kind: String?) = when (kind) {
    "income" -> tx("Ingreso", "Income"); "debt" -> tx("Cuota", "Instalment"); "goal" -> tx("Meta", "Goal"); else -> tx("Pago", "Payment")
}

/** E10 — recurring payments (Basic): create, pause/activate, delete. */
@Composable
fun RecurringScreen(model: AppModel, nav: Navigator) {
    val list = rememberLoad(model) { model.api.recurring() }
    var creating by remember { mutableStateOf(false) }
    var deleting by remember { mutableStateOf<RecurringItem?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) { model.recordScreen("recurring_opened", "recurring") }
    DetailScaffold(tx("Pagos recurrentes", "Recurring payments"), nav::back, actions = {
        IconButton({ creating = true }, modifier = Modifier.heightIn(min = 48.dp)) { Icon(Icons.Rounded.Add, contentDescription = tx("Agregar recurrente", "Add recurring")) }
    }) {
        LoadContent(list) { l ->
            DincrCard { Column { AmountLine(tx("Gastos fijos por mes", "Fixed expenses per month"), l.monthlyExpenses, emphasize = true); InfoLine(tx("Activos", "Active"), l.items.count { it.isActive == true }.toString()) } }
            if (l.items.isEmpty()) EmptyState(Icons.Rounded.Repeat, tx("Sin pagos recurrentes", "No recurring payments"), tx("Agregá suscripciones, alquiler o servicios para planificar mejor.", "Add subscriptions, rent or utilities to plan better.")) {
                DincrPrimaryButton(tx("Agregar", "Add"), { creating = true })
            }
            l.items.forEach { item ->
                DincrCard {
                    Column {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(item.name.orEmpty(), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
                                Caption(listOfNotNull(item.category, frequencyLabel(item.frequency), item.dueDay?.let { tx("día $it", "day $it") }).joinToString(" · "))
                            }
                            MoneyText(item.amount, sign = if (item.itemType == "income") com.dincr.data.MoneyFormat.Sign.INCOME else com.dincr.data.MoneyFormat.Sign.NONE)
                        }
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            val active = item.isActive == true
                            val label = if (active) tx("Activo", "Active") else tx("En pausa", "Paused")
                            Text(label, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2, modifier = Modifier.weight(1f))
                            Switch(active, onCheckedChange = { on ->
                                if (busy) return@Switch
                                val amount = item.amount ?: return@Switch
                                busy = true
                                scope.launch {
                                    // Only the editable fields are sent (never the whole stored row).
                                    val request = RecurringRequest(item.name.orEmpty(), amount, item.category ?: "general", item.itemType ?: "expense", item.frequency ?: "monthly", item.dueDay, on)
                                    model.load(tx("No pudimos cambiarlo.", "We couldn’t change it.")) { model.api.updateRecurring(item.id, request, IdempotencyKey.new()) }
                                        .onSuccess { list.reload() }.onFailure { if (it !is AuthException.SignedOut) model.showNotice(it.message.orEmpty()) }
                                    busy = false
                                }
                            }, modifier = Modifier.semantics { contentDescription = "${item.name.orEmpty()}: $label" })
                            TextButton({ deleting = item }, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Eliminar", "Delete"), color = Dincr.colors.negative) }
                        }
                    }
                }
            }
        }
    }
    if (creating) RecurringForm(model, onDismiss = { creating = false }) { creating = false; list.reload(); model.showNotice(it) }
    deleting?.let { item ->
        ConfirmDialog(tx("¿Eliminar «${item.name.orEmpty()}»?", "Delete “${item.name.orEmpty()}”?"), tx("No se puede deshacer.", "This can’t be undone."), tx("Eliminar", "Delete"), busy = busy, onDismiss = { deleting = null }, onConfirm = {
            busy = true
            scope.launch {
                val result = model.load(tx("No pudimos eliminarlo.", "We couldn’t delete it.")) { model.api.deleteRecurring(item.id) }
                busy = false; deleting = null
                if (result.isSuccess || (result.exceptionOrNull() as? ApiError)?.kind == ApiError.Kind.NOT_FOUND) list.reload()
                else result.exceptionOrNull()?.takeIf { it !is AuthException.SignedOut }?.message?.let(model::showNotice)
            }
        })
    }
}

fun frequencyLabel(frequency: String?) = when (frequency) {
    "weekly" -> tx("Semanal", "Weekly"); "biweekly" -> tx("Quincenal", "Every two weeks"); "quarterly" -> tx("Trimestral", "Quarterly")
    "annual" -> tx("Anual", "Yearly"); else -> tx("Mensual", "Monthly")
}

@Composable
private fun RecurringForm(model: AppModel, onDismiss: () -> Unit, onSaved: (String) -> Unit) {
    val format = Dincr.money
    var name by remember { mutableStateOf("") }
    var amount by remember { mutableStateOf("") }
    var category by remember { mutableStateOf("") }
    var type by remember { mutableStateOf("expense") }
    var frequency by remember { mutableStateOf("monthly") }
    var day by remember { mutableStateOf("") }
    var errors by remember { mutableStateOf(mapOf<String, String>()) }
    var error by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    val key = remember { IdempotencyKey.new() }
    val scope = rememberCoroutineScope()
    FormSheet(tx("Nuevo pago recurrente", "New recurring payment"), saving, error, tx("Guardar", "Save"), onDismiss = onDismiss, onPrimary = {
        val found = mutableMapOf<String, String>()
        if (name.isBlank()) found["name"] = tx("Escribí un nombre.", "Enter a name.")
        val amountValue = AmountInput.parse(amount, format.separators).also { if (it == null) found["amount"] = tx("Escribí un monto mayor que cero.", "Enter an amount above zero.") }
        val dayValue = if (day.isBlank()) null else WholeNumberInput.parse(day, 1..31).also { if (it == null) found["day"] = tx("Entre 1 y 31.", "1 to 31.") }
        errors = found
        if (found.isNotEmpty() || amountValue == null) return@FormSheet
        saving = true; error = null
        scope.launch {
            model.load(tx("No pudimos guardarlo.", "We couldn’t save it.")) {
                model.api.createRecurring(RecurringRequest(name.trim(), amountValue, category.trim().ifEmpty { "general" }, type, frequency, dayValue, true), key)
            }.onSuccess { onSaved(tx("Pago recurrente agregado", "Recurring payment added")) }.onFailure { if (it !is AuthException.SignedOut) error = it.message }
            saving = false
        }
    }) {
        FormField(tx("Nombre", "Name"), name, { name = it }, errors["name"])
        MoneyField(tx("Monto", "Amount"), amount, { amount = it }, errors["amount"])
        FormField(tx("Categoría", "Category"), category, { category = it })
        ChoiceChips(listOf("expense" to tx("Gasto", "Expense"), "income" to tx("Ingreso", "Income")), type, { type = it }, tx("Tipo", "Type"))
        ChoiceChips(listOf("weekly", "biweekly", "monthly", "quarterly", "annual").map { it to frequencyLabel(it) }, frequency, { frequency = it }, tx("Frecuencia", "Frequency"))
        FormField(tx("Día de pago (opcional)", "Due day (optional)"), day, { day = it }, errors["day"], KeyboardType.Number)
    }
}

/** Reports (Basic; `advanced_reports`): a month with the previous one. */
@Composable
fun ReportsScreen(model: AppModel, nav: Navigator) {
    var month by remember { mutableStateOf(YearMonth.now()) }
    val paused = !model.isOn(OpsFlag.ADVANCED_REPORTS)
    val report = rememberLoad(model, month) { model.api.report(month.toString()) }
    LaunchedEffect(Unit) { model.recordScreen("reports_opened", "reports") }
    DetailScaffold(tx("Reportes", "Reports"), nav::back) {
        if (paused) { FeaturePaused(model, OpsFlag.ADVANCED_REPORTS); return@DetailScaffold }
        MonthPicker(month, { month = it })
        LoadContent(report) { r ->
            DincrCard {
                Column {
                    AmountLine(tx("Ingresos", "Income"), r.income, sign = com.dincr.data.MoneyFormat.Sign.INCOME)
                    AmountLine(tx("Gastos", "Expenses"), r.expenses)
                    AmountLine(tx("Pagos de deuda", "Debt payments"), r.debtPaid)
                    AmountLine(tx("Aportes a metas", "Goal contributions"), r.goalContributions)
                    AmountLine(tx("Balance", "Balance"), r.balance, emphasize = true)
                }
            }
            r.comparison?.let { c ->
                Section(tx("Mes anterior", "Previous month")) {
                    AmountLine(tx("Ingresos", "Income"), c.income)
                    AmountLine(tx("Gastos", "Expenses"), c.expenses)
                }
            }
            if (r.categories.isNotEmpty()) Section(tx("Gastos por categoría", "Expenses by category")) {
                CategoryBars(r.categories.map { (it.category ?: tx("Sin categoría", "Uncategorized")) to (it.amount ?: BigDecimal.ZERO) })
            }
        }
    }
}

/** B17 — a paused feature shows the server's message instead of the screen. */
@Composable
fun FeaturePaused(model: AppModel, flag: OpsFlag) {
    com.dincr.design.StatusBanner(com.dincr.design.BannerTone.WARNING, tx("En mantenimiento", "Under maintenance"),
        model.flags.value.message(flag, com.dincr.data.AppLanguage.current()) ?: tx("Esta función está en pausa por mantenimiento. Intentá más tarde.", "This feature is paused for maintenance. Please try later."))
}
