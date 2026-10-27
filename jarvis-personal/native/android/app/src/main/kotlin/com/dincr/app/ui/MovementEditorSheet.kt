package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.material3.Switch
import androidx.compose.ui.Alignment
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
import com.dincr.data.PaidWithChange
import com.dincr.data.PaidWithOptions
import androidx.compose.runtime.LaunchedEffect
import kotlinx.coroutines.async
import kotlinx.coroutines.CancellationException
import com.dincr.design.Dincr
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.ErrorState
import com.dincr.design.TabularNums
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneOffset
import kotlinx.coroutines.launch
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.data.ConversionPreview
import com.dincr.data.ExchangeRateInput
import com.dincr.data.IdempotencyKey

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
fun MovementEditorSheet(
    model: AppModel, mode: EditorMode, onDismiss: () -> Unit, onSaved: (String) -> Unit, onDelete: (Movement) -> Unit, latestRate: BigDecimal? = null,
    /** What a new movement starts as (Hoy opens it as an income to register the month's pay). */
    initialKind: MovementKind = MovementKind.EXPENSE,
) {
    val format = Dincr.money
    val profile by model.profile.collectAsStateWithLifecycle()
    val editing = (mode as? EditorMode.Edit)?.movement
    val base = (profile?.baseCurrency ?: "CRC").uppercase()
    val entryCurrencies = profile?.entryCurrencies.orEmpty().map { it.uppercase() }
    // Another currency is offered only when this backend converts it for the account (#269), and
    // on edit only for manual income/expense rows (the backend refuses it for anything else).
    val otherCurrency = entryCurrencies.firstOrNull { it != base }?.takeIf { base in entryCurrencies && (editing == null || editing.acceptsCurrency) }
    val storedForeign = editing?.takeIf { it.isCurrencyEditable(entryCurrencies) }
    // A dollar expense still waiting for the close: edited in its own currency, without a rate.
    val storedPending = editing?.takeIf { it.isPendingConversion }
    var kind by remember { mutableStateOf(editing?.kind ?: initialKind) }
    var currency by remember { mutableStateOf((storedForeign ?: storedPending)?.originalCurrency?.uppercase() ?: base) }
    // A row typed in another currency is edited in that currency (its original amount).
    val prefilledAmount = remember { editing?.let { (storedForeign ?: storedPending)?.originalAmount?.let(format::inputText) ?: format.inputText(it.amount) } ?: "" }
    var amountText by remember { mutableStateOf(prefilledAmount) }
    val prefilledRate = remember { (storedForeign?.exchangeRate ?: latestRate)?.let(format::inputText) ?: "" }
    var rateText by remember { mutableStateOf(prefilledRate) }
    var rateError by remember { mutableStateOf<String?>(null) }
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
    // "Pagado con": the user's own accounts and cards (empty while unavailable or without any).
    var paidWithOptions by remember { mutableStateOf(emptyList<PaidWithOptions.Option>()) }
    var paidWith by remember { mutableStateOf(editing?.financialAccountId) }
    // A dollar expense may keep its dollars until the close (PendingConversion), while the server allows it.
    var pendingAvailable by remember { mutableStateOf(false) }
    var waitsForClose by remember { mutableStateOf(storedForeign == null) }
    LaunchedEffect(Unit) {
        // Read together, so the sheet settles once (a late second answer would redraw it mid-typing).
        val offered = async { try { model.api.paidWithOptions().offered } catch (e: CancellationException) { throw e } catch (_: Exception) { emptyList() } }
        val available = async { try { model.api.pendingConversion().available } catch (e: CancellationException) { throw e } catch (_: Exception) { false } }
        val (options, pendingOk) = offered.await() to available.await()
        paidWithOptions = options
        pendingAvailable = pendingOk
    }
    // Only a manual expense in the other currency may wait; one already waiting keeps the choice (so it can be converted).
    val offersWaitForClose = kind == MovementKind.EXPENSE && currency != base &&
        (if (editing == null) pendingAvailable else editing.origin == "expense" && (pendingAvailable || storedPending != null))
    val waits = offersWaitForClose && waitsForClose
    // Only a manual expense says what paid it.
    val showsPaidWith = kind == MovementKind.EXPENSE && paidWithOptions.isNotEmpty() && (editing == null || editing.origin == "expense")
    val scope = rememberCoroutineScope()
    val haptics = LocalHapticFeedback.current
    val sheet = rememberModalBottomSheetState(skipPartiallyExpanded = true)

    fun save() {
        if (saving) return
        val foreign = currency != base
        // Untouched on edit: send the stored value, digit for digit (the original amount and the
        // user's own rate for a row in another currency, so the backend recomputes the same base).
        val amount = when {
            editing != null && amountText == prefilledAmount && foreign && storedForeign != null && currency == storedForeign.originalCurrency?.uppercase() -> storedForeign.originalAmount
            editing != null && amountText == prefilledAmount && foreign && storedPending != null && currency == storedPending.originalCurrency?.uppercase() -> storedPending.originalAmount
            editing != null && amountText == prefilledAmount && !foreign && storedForeign == null && storedPending == null -> editing.amount
            else -> AmountInput.parse(amountText, format.separators)
        }
        val rate = when {
            !foreign || waits -> null
            storedForeign != null && rateText == prefilledRate && storedForeign.exchangeRate != null -> storedForeign.exchangeRate
            else -> ExchangeRateInput.parse(rateText, format.separators)
        }
        val example = format.format(BigDecimal(18450)).removePrefix(format.symbol).trim()
        amountError = if (amount == null) tx("Escribí un monto mayor que cero, por ejemplo $example.", "Enter an amount above zero, for example $example.") else null
        rateError = if (foreign && !waits && rate == null) tx("Escribí cuántos colones vale 1 dólar (mayor que cero).", "Enter how many colones 1 dollar is worth (above zero).") else null
        descriptionError = if (description.isBlank()) tx("Escribí una descripción.", "Enter a description.") else null
        if (amount == null || (foreign && !waits && rate == null) || description.isBlank()) { haptics.performHapticFeedback(HapticFeedbackType.Reject); return }
        val sentCurrency = if (foreign) currency else null
        saving = true; saveError = null
        scope.launch {
            val result = model.load(tx("No pudimos guardar. Revisá tu conexión e intentá de nuevo.", "We couldn’t save. Check your connection and try again.")) {
                if (editing == null) {
                    val entry = EntryCreate(amount, description.trim(), category, date.toString(), sentCurrency, rate,
                        financialAccountId = if (showsPaidWith) paidWith else null, convertAtClose = if (waits) true else null)
                    val key = submission?.takeIf { it.first == entry }?.second ?: IdempotencyKey.new()
                    submission = entry to key
                    model.api.create(kind, entry, key)
                } else {
                    // Untouched, the stored link is left as it is (never rewritten by another edit).
                    val paidWithChange = if (showsPaidWith && paidWith != editing.financialAccountId) PaidWithChange.Set(paidWith) else PaidWithChange.Unchanged
                    model.api.update(editing.movementId, MovementUpdate(date.toString(), description.trim(), amount, editing.transactionType ?: "expense", category, editing.notes.orEmpty(), sentCurrency, rate,
                        convertAtClose = if (waits) true else null), paidWithChange)
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
            val errors = listOfNotNull(amountError, rateError, descriptionError)
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
            if (otherCurrency != null) {
                SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth()) {
                    listOf(base, otherCurrency).forEachIndexed { i, code ->
                        SegmentedButton(currency == code, { currency = code; amountError = null; rateError = null }, SegmentedButtonDefaults.itemShape(i, 2)) {
                            Text(if (code == "CRC") tx("Colones", "Colones") else if (code == "USD") tx("Dólares", "Dollars") else code)
                        }
                    }
                }
            }
            val symbol = if (currency == base) format.symbol else format.copy(currency = currency).symbol
            OutlinedTextField(amountText, { amountText = it; amountError = null }, label = { Text(tx("Monto", "Amount")) }, prefix = { Text(symbol) },
                textStyle = MaterialTheme.typography.headlineSmall.merge(TabularNums), singleLine = true, isError = amountError != null,
                supportingText = amountError?.let { { Text(it) } }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                modifier = Modifier.fillMaxWidth().testTag("editor.amount"))
            if (offersWaitForClose) {
                Row(Modifier.fillMaxWidth().heightIn(min = 48.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(tx("Convertir al cierre", "Convert at the close"), style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text)
                        Text(if (waits) tx("Queda en dólares hasta el corte de la tarjeta (o fin de mes sin tarjeta); ahí se convierte con un solo tipo de cambio.",
                                "It stays in dollars until the card’s statement cut (or month end without a card), then converts with one rate.")
                            else tx("Se convierte ahora con tu tipo de cambio.", "It converts now with your rate."),
                            style = MaterialTheme.typography.bodySmall, color = Dincr.colors.textMuted)
                    }
                    Switch(waitsForClose, { waitsForClose = it; rateError = null }, Modifier.testTag("editor.waitForClose"))
                }
            }
            if (currency != base && !waits) {
                OutlinedTextField(rateText, { rateText = it; rateError = null }, label = { Text(tx("Tipo de cambio (₡ por US\$1)", "Exchange rate (₡ per US\$1)")) },
                    singleLine = true, isError = rateError != null,
                    supportingText = { Text(rateError ?: tx("Usá el tipo de cambio de tu banco. DINCR no lo inventa.", "Use your bank’s rate. DINCR never makes one up.")) },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.fillMaxWidth().testTag("editor.rate"))
                val typed = AmountInput.parse(amountText, format.separators)
                val typedRate = ExchangeRateInput.parse(rateText, format.separators)
                ConversionPreview.baseAmount(typed, currency, base, typedRate)?.let { converted ->
                    Text(tx("Se registra como ${format.format(converted)}", "Recorded as ${format.format(converted)}"), style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2)
                }
            }
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
            if (showsPaidWith) {
                var paidWithOpen by remember { mutableStateOf(false) }
                val chosen = paidWithOptions.firstOrNull { it.id == paidWith }?.label
                    ?: if (paidWith != null) tx("Cuenta guardada", "Saved account") else tx("Sin indicar", "Not set")
                ExposedDropdownMenuBox(paidWithOpen, { paidWithOpen = it }) {
                    OutlinedTextField(chosen, {}, readOnly = true, label = { Text(tx("Pagado con", "Paid with")) }, trailingIcon = { ExposedDropdownMenuDefaults.TrailingIcon(paidWithOpen) },
                        modifier = Modifier.fillMaxWidth().menuAnchor(MenuAnchorType.PrimaryNotEditable).testTag("editor.paidWith"))
                    ExposedDropdownMenu(paidWithOpen, { paidWithOpen = false }) {
                        DropdownMenuItem({ Text(tx("Sin indicar", "Not set")) }, { paidWith = null; paidWithOpen = false })
                        paidWithOptions.forEach { option -> DropdownMenuItem({ Text(option.label) }, { paidWith = option.id; paidWithOpen = false }) }
                    }
                }
            }
            saveError?.let { ErrorState(it) }
            DincrPrimaryButton(tx("Guardar", "Save"), ::save, loading = saving, modifier = Modifier.testTag("editor.save"))
            Row { if (editing != null && editing.canEdit(entryCurrencies)) TextButton({ onDelete(editing) }) { Text(tx("Eliminar movimiento", "Delete transaction"), color = Dincr.colors.negative) } }
        }
    }

    if (pickingDate) {
        val picker = rememberDatePickerState(initialSelectedDateMillis = date.atStartOfDay().toInstant(ZoneOffset.UTC).toEpochMilli())
        DatePickerDialog(onDismissRequest = { pickingDate = false }, confirmButton = {
            TextButton({ picker.selectedDateMillis?.let { date = Instant.ofEpochMilli(it).atZone(ZoneOffset.UTC).toLocalDate() }; pickingDate = false }) { Text(tx("Listo", "Done")) }
        }, dismissButton = { TextButton({ pickingDate = false }) { Text(tx("Cancelar", "Cancel")) } }) { DatePicker(picker) }
    }
}

