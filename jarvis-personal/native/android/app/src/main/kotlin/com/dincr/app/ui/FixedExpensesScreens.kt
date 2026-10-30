package com.dincr.app.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.Repeat
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AuthException
import com.dincr.data.CorrectionInput
import com.dincr.data.Jarvis
import com.dincr.data.OwnerFixedExpense
import com.dincr.data.OwnerFixedExpenseRequest
import com.dincr.data.WholeNumberInput
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.EmptyState
import com.dincr.design.MoneyText
import java.math.BigDecimal
import kotlinx.coroutines.launch

/**
 * FX-1 — Plan → Gastos fijos (VIP and the Owner): what is paid every month, to see, add, edit and
 * remove. VIP: its recurring expenses ([RecurringScreen] in expenses-only mode, the obligations its
 * Salvavidas reads). The Owner: his `fixed_expenses` (what his Salvavidas and strategy read), through
 * the Owner-only `/finance/fixed-expenses`. Removing deactivates the row. iOS twin: `FixedExpensesViews.swift`.
 */
@Composable
fun FixedExpensesScreen(model: AppModel, nav: Navigator) {
    val profile by model.profile.collectAsStateWithLifecycle()
    if (Jarvis.isAvailable(profile)) OwnerFixedExpensesScreen(model, nav) else RecurringScreen(model, nav, expensesOnly = true)
}

internal fun intervalLabel(months: Int?): String {
    val value = maxOf(months ?: 1, 1)
    return if (value == 1) tx("Cada mes", "Every month") else tx("Cada $value meses", "Every $value months")
}

@Composable
private fun OwnerFixedExpensesScreen(model: AppModel, nav: Navigator) {
    val list = rememberLoad(model) { model.api.ownerFixedExpenses() }
    var creating by remember { mutableStateOf(false) }
    var editing by remember { mutableStateOf<OwnerFixedExpense?>(null) }
    var removing by remember { mutableStateOf<OwnerFixedExpense?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    DetailScaffold(tx("Gastos fijos", "Fixed expenses"), nav::back, actions = {
        IconButton({ creating = true }, modifier = Modifier.heightIn(min = 48.dp).testTag("fixedExpenses.add")) {
            Icon(Icons.Rounded.Add, contentDescription = tx("Agregar gasto fijo", "Add fixed expense"))
        }
    }) {
        LoadContent(list) { items ->
            if (items.isEmpty()) {
                EmptyState(Icons.Rounded.Repeat, tx("Todavía no hay gastos fijos", "No fixed expenses yet"), tx("Agregá lo que pagás todos los meses.", "Add what you pay every month.")) {}
            } else {
                DincrCard {
                    Column(Modifier.testTag("fixedExpenses.total")) {
                        AmountLine(tx("Total por mes", "Total per month"), items.mapNotNull { it.monthlyAmount }.fold(BigDecimal.ZERO, BigDecimal::add), emphasize = true)
                    }
                }
            }
            items.forEach { item ->
                DincrCard {
                    Column(Modifier.testTag("fixedExpenses.row.${item.id}")) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(item.name.orEmpty(), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
                                Caption(listOfNotNull(intervalLabel(item.intervalMonths), item.dueDay?.let { tx("día $it", "day $it") }, item.category).joinToString(" · "))
                            }
                            MoneyText(item.expectedAmount, currency = item.currency)
                        }
                        Row {
                            TextButton({ editing = item }, modifier = Modifier.heightIn(min = 48.dp).testTag("fixedExpenses.edit.${item.id}")) {
                                Text(tx("Editar", "Edit"), color = Dincr.colors.tint)
                            }
                            TextButton({ removing = item }, modifier = Modifier.heightIn(min = 48.dp).testTag("fixedExpenses.remove.${item.id}")) {
                                Text(tx("Quitar", "Remove"), color = Dincr.colors.negative)
                            }
                        }
                    }
                }
            }
        }
    }
    if (creating) OwnerFixedExpenseForm(model, null, onDismiss = { creating = false }) { creating = false; list.reload(); model.showNotice(it) }
    editing?.let { item -> OwnerFixedExpenseForm(model, item, onDismiss = { editing = null }) { editing = null; list.reload(); model.showNotice(it) } }
    removing?.let { item ->
        ConfirmDialog(tx("¿Quitar «${item.name.orEmpty()}»?", "Remove “${item.name.orEmpty()}”?"),
            tx("Deja de contarse en tu Salvavidas y tu plan.", "It stops counting in your emergency fund and your plan."), tx("Quitar", "Remove"), busy = busy,
            onDismiss = { removing = null }, onConfirm = {
                busy = true
                scope.launch {
                    model.load(tx("No pudimos quitarlo.", "We couldn’t remove it.")) { model.api.removeOwnerFixedExpense(item.id) }
                        .onSuccess { list.reload(); model.showNotice(tx("Gasto fijo quitado", "Fixed expense removed")) }
                        .onFailure { if (it !is AuthException.SignedOut) model.showNotice(it.message.orEmpty()) }
                    busy = false; removing = null
                }
            })
    }
}

/** Adds a fixed expense, or edits one (name, amount, category, every how many months, day). */
@Composable
private fun OwnerFixedExpenseForm(model: AppModel, editing: OwnerFixedExpense?, onDismiss: () -> Unit, onSaved: (String) -> Unit) {
    val format = Dincr.money
    var name by remember { mutableStateOf(editing?.name.orEmpty()) }
    var amount by remember { mutableStateOf(editing?.expectedAmount?.let(format::inputText).orEmpty()) }
    var category by remember { mutableStateOf(editing?.category ?: "Gastos fijos") }
    var interval by remember { mutableStateOf(editing?.intervalMonths?.takeIf { it in OwnerFixedExpenseRequest.INTERVALS } ?: 1) }
    var day by remember { mutableStateOf(editing?.dueDay?.toString().orEmpty()) }
    var error by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    FormSheet(if (editing == null) tx("Nuevo gasto fijo", "New fixed expense") else tx("Editar gasto fijo", "Edit fixed expense"), saving, error, tx("Guardar", "Save"),
        onDismiss = onDismiss, onPrimary = {
            val value = CorrectionInput.amount(amount, format.separators)
            val dueDay = if (day.isBlank()) null else WholeNumberInput.parse(day, 1..31) ?: 0
            OwnerFixedExpenseRequest.problem(name, value, interval, dueDay, spanish = tx("es", "en") == "es")?.let { error = it; return@FormSheet }
            val request = OwnerFixedExpenseRequest(name.trim(), category.trim().ifEmpty { "Gastos fijos" }, value!!, interval, dueDay)
            saving = true; error = null
            scope.launch {
                model.load(tx("No pudimos guardar.", "We couldn’t save.")) {
                    if (editing == null) model.api.createOwnerFixedExpense(request) else model.api.updateOwnerFixedExpense(editing.id, request)
                }.onSuccess { onSaved(if (editing == null) tx("Gasto fijo agregado", "Fixed expense added") else tx("Gasto fijo actualizado", "Fixed expense updated")) }
                    .onFailure { if (it !is AuthException.SignedOut) error = it.message }
                saving = false
            }
        }) {
        FormField(tx("Nombre", "Name"), name, { name = it }, modifier = Modifier.testTag("fixedExpenses.name"))
        MoneyField(tx("Monto", "Amount"), amount, { amount = it }, modifier = Modifier.testTag("fixedExpenses.amount"))
        FormField(tx("Categoría", "Category"), category, { category = it })
        ChoiceChips(OwnerFixedExpenseRequest.INTERVALS.map { it to intervalLabel(it) }, interval, { interval = it }, tx("Se paga", "Paid"))
        FormField(tx("Día de pago (1–31, opcional)", "Payment day (1–31, optional)"), day, { day = it }, keyboard = KeyboardType.Number)
    }
}
