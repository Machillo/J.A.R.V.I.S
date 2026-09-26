package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.DatePicker
import androidx.compose.material3.DatePickerDialog
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MenuAnchorType
import androidx.compose.material3.ExposedDropdownMenuBox
import androidx.compose.material3.ExposedDropdownMenuDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberDatePickerState
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AmountInput
import com.dincr.data.ApiError
import com.dincr.data.AuthException
import com.dincr.data.EntryCreate
import com.dincr.data.Movement
import com.dincr.data.MovementKind
import com.dincr.data.MovementUpdate
import com.dincr.design.Dincr
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.ErrorState
import com.dincr.design.TabularNums
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset
import java.util.UUID
import kotlinx.coroutines.launch

sealed interface EditorMode { data object Create : EditorMode; data class Edit(val movement: Movement) : EditorMode }

private val expenseCategories = listOf("Comida", "Vivienda", "Servicios", "Internet", "Teléfono", "Transporte", "Gasolina", "Restaurante", "Salud", "Entretenimiento", "Compras", "Seguros", "Deporte", "Mascotas", "Otros")
private val incomeCategories = listOf("Salario", "Boleta de pago", "Bono", "Reembolso", "Otros ingresos")

/**
 * PARITY D3/D4/D5 — bottom sheet form: visible labels, inline errors, summary for 2+ errors,
 * single-flight save. An edit sends back exactly what is stored unless the user changes it: the
 * amount is prefilled unrounded and the stored category stays selectable.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MovementEditorSheet(model: AppModel, mode: EditorMode, onDismiss: () -> Unit, onSaved: (String) -> Unit, onDelete: (Movement) -> Unit) {
    val format = Dincr.money
    val editing = (mode as? EditorMode.Edit)?.movement
    var kind by remember { mutableStateOf(editing?.kind ?: MovementKind.EXPENSE) }
    val prefilledAmount = remember { editing?.let { format.inputText(it.amount) } ?: "" }
    var amountText by remember { mutableStateOf(prefilledAmount) }
    var description by remember { mutableStateOf(editing?.description.orEmpty()) }
    val storedCategory = editing?.category?.takeIf { it.isNotEmpty() }
    val baseCategories = if (kind == MovementKind.INCOME) incomeCategories else expenseCategories
    val categories = if (storedCategory != null && storedCategory !in baseCategories) listOf(storedCategory) + baseCategories else baseCategories
    var category by remember { mutableStateOf(storedCategory ?: categories.first()) }
    // One key per distinct submission: a retry of the same body reuses it, so the backend answers
    // from the first request instead of creating a second movement.
    var submission by remember { mutableStateOf<Pair<EntryCreate, String>?>(null) }
    var date by remember { mutableStateOf(editing?.day?.let { runCatching { LocalDate.parse(it) }.getOrNull() } ?: LocalDate.now()) }
    var amountError by remember { mutableStateOf<String?>(null) }
    var descriptionError by remember { mutableStateOf<String?>(null) }
    var saveError by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    var pickingDate by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val haptics = LocalHapticFeedback.current
    val sheet = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    fun save() {
        if (saving) return
        // Untouched on edit: send the stored value, digit for digit.
        val amount = if (editing != null && amountText == prefilledAmount) editing.amount else AmountInput.parse(amountText, format.separators)
        val example = format.format(BigDecimal(18450)).removePrefix(format.symbol).trim()
        amountError = if (amount == null) tx("Escribí un monto mayor que cero, por ejemplo $example.", "Enter an amount above zero, for example $example.") else null
        descriptionError = if (description.isBlank()) tx("Escribí una descripción.", "Enter a description.") else null
        if (amount == null || description.isBlank()) { haptics.performHapticFeedback(HapticFeedbackType.Reject); return }
        saving = true; saveError = null
        scope.launch {
            val result = model.load(tx("No pudimos guardar. Revisá tu conexión e intentá de nuevo.", "We couldn’t save. Check your connection and try again.")) {
                if (editing == null) {
                    val entry = EntryCreate(amount, description.trim(), category, date.toString())
                    val key = submission?.takeIf { it.first == entry }?.second ?: UUID.randomUUID().toString()
                    submission = entry to key
                    model.service.create(kind, entry, key)
                } else {
                    model.service.update(editing.movementId, MovementUpdate(date.toString(), description.trim(), amount, editing.transactionType ?: "expense", category, editing.notes.orEmpty()))
                }
            }
            saving = false
            val error = result.exceptionOrNull()
            when {
                error == null -> {
                    haptics.performHapticFeedback(HapticFeedbackType.Confirm)
                    onSaved(if (editing != null) tx("Cambios guardados", "Changes saved") else if (kind == MovementKind.INCOME) tx("Ingreso guardado", "Income saved") else tx("Gasto guardado", "Expense saved"))
                }
                // Deleted or locked elsewhere: nothing to save; the list refreshes and says so.
                editing != null && (error as? ApiError)?.kind == ApiError.Kind.NOT_FOUND ->
                    onSaved(tx("Ese movimiento ya no existe. Actualizamos la lista.", "That transaction no longer exists. The list was refreshed."))
                error is AuthException.SignedOut -> Unit
                else -> {
                    saveError = error.message
                    haptics.performHapticFeedback(HapticFeedbackType.Reject)
                }
            }
        }
    }

    ModalBottomSheet(onDismissRequest = { if (!saving) onDismiss() }, sheetState = sheet, containerColor = Dincr.colors.surface) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).imePadding().navigationBarsPadding().padding(horizontal = DincrSpacing.s4, vertical = DincrSpacing.s2), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s4)) {
            Text(if (editing != null) tx("Editar movimiento", "Edit transaction") else tx("Nuevo movimiento", "New transaction"), style = MaterialTheme.typography.headlineSmall, color = Dincr.colors.text)
            val errors = listOfNotNull(amountError, descriptionError)
            if (errors.size > 1) {
                Column(Modifier.semantics { liveRegion = LiveRegionMode.Polite }) {
                    Text(tx("Revisá ${errors.size} campos", "Check ${errors.size} fields"), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.negative)
                    errors.forEach { Text("• $it", style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.negative) }
                }
            }
            if (editing == null) {
                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                    listOf(MovementKind.EXPENSE to tx("Gasto", "Expense"), MovementKind.INCOME to tx("Ingreso", "Income")).forEachIndexed { i, (k, label) ->
                        SegmentedButton(kind == k, { kind = k; if (category !in (if (k == MovementKind.INCOME) incomeCategories else expenseCategories)) category = (if (k == MovementKind.INCOME) incomeCategories else expenseCategories).first() }, SegmentedButtonDefaults.itemShape(i, 2)) { Text(label) }
                    }
                }
            }
            OutlinedTextField(amountText, { amountText = it; amountError = null }, label = { Text(tx("Monto", "Amount")) }, prefix = { Text(format.symbol) },
                textStyle = MaterialTheme.typography.headlineSmall.merge(TabularNums), singleLine = true, isError = amountError != null,
                supportingText = amountError?.let { { Text(it) } }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                modifier = Modifier.fillMaxWidth().testTag("editor.amount"))
            OutlinedTextField(description, { description = it; descriptionError = null }, label = { Text(tx("Descripción", "Description")) }, singleLine = true,
                isError = descriptionError != null, supportingText = descriptionError?.let { { Text(it) } }, modifier = Modifier.fillMaxWidth().testTag("editor.description"))
            var expanded by remember { mutableStateOf(false) }
            ExposedDropdownMenuBox(expanded, { expanded = it }) {
                OutlinedTextField(category, {}, readOnly = true, label = { Text(tx("Categoría", "Category")) }, trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(expanded) },
                    modifier = Modifier.fillMaxWidth().menuAnchor(MenuAnchorType.PrimaryNotEditable))
                ExposedDropdownMenu(expanded, { expanded = false }) {
                    categories.forEach { option -> DropdownMenuItem({ Text(option) }, { category = option; expanded = false }) }
                }
            }
            OutlinedButton({ pickingDate = true }, Modifier.fillMaxWidth().heightIn(min = 52.dp)) { Text("${tx("Fecha", "Date")}: ${dayLabel(date.toString())}") }
            saveError?.let { ErrorState(it) }
            DincrPrimaryButton(tx("Guardar", "Save"), ::save, loading = saving, modifier = Modifier.testTag("editor.save"))
            Row { if (editing != null && editing.editable) TextButton({ onDelete(editing) }) { Text(tx("Eliminar movimiento", "Delete transaction"), color = Dincr.colors.negative) } }
        }
    }

    if (pickingDate) {
        val picker = rememberDatePickerState(initialSelectedDateMillis = date.atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli())
        DatePickerDialog(onDismissRequest = { pickingDate = false }, confirmButton = {
            TextButton({ picker.selectedDateMillis?.let { date = Instant.ofEpochMilli(it).atZone(ZoneOffset.UTC).toLocalDate() }; pickingDate = false }) { Text(tx("Listo", "Done")) }
        }, dismissButton = { TextButton({ pickingDate = false }) { Text(tx("Cancelar", "Cancel")) } }) { DatePicker(picker) }
    }
}

