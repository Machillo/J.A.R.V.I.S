package com.dincr.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.CreditCard
import androidx.compose.material.icons.rounded.Payments
import androidx.compose.material.icons.rounded.PieChart
import androidx.compose.material.icons.rounded.Redeem
import androidx.compose.material.icons.rounded.Shield
import androidx.compose.material3.IconButton
import androidx.compose.material3.Icon
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AmountInput
import com.dincr.data.ApiError
import com.dincr.data.AuthException
import com.dincr.data.Debt
import com.dincr.data.DebtRequest
import com.dincr.data.Feature
import com.dincr.data.IdempotencyKey
import com.dincr.data.InterestRateInput
import com.dincr.data.PlanTier
import com.dincr.data.WholeNumberInput
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.EmptyState
import com.dincr.design.MoneyText
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal
import java.time.LocalDate
import kotlinx.coroutines.launch

/**
 * E1 — the Plan tab: exactly Aguinaldo, Tu plan del mes (UX-3: Estrategia + Distribución as one
 * plan; the row keeps the Estrategia route and gate), Deudas (UX-4: where debts are managed, every
 * plan; Hoy keeps a shortcut), Ingresos y base (UX-7: the declared income and essential expenses, every plan), Salvavidas and Distribución de dinero (kept as a transitional access
 * until its retirement is approved), each behind its historical plan gate. A row the plan does not
 * include stays visible, locked, and opens the plans screen. The Owner passes every gate by the
 * server role ([Profile.planTier]). Goals live in Hoy; budget, calendar and recurring payments in
 * Perfil → Finanzas.
 */
@Composable
fun PlanHubScreen(model: AppModel, nav: Navigator) {
    val profile by model.profile.collectAsStateWithLifecycle()
    val plan = profile?.planTier ?: PlanTier.FREE
    ScreenColumn {
        Text(tx("Plan", "Plan"), style = MaterialTheme.typography.headlineMedium, color = Dincr.colors.text)
        DincrCard {
            Column {
                PlanRow(plan.allows(Feature.GMAIL_AUTOMATION), PlanTier.VIP, Icons.Rounded.Redeem, tx("Aguinaldo", "Aguinaldo"),
                    tx("Estimación con las órdenes de la CCSS", "Estimate from CCSS payroll notices"), nav, "aguinaldo")
                PlanRow(plan.allows(Feature.STRATEGY_BASIC), PlanTier.BASIC, Icons.Rounded.AutoAwesome, tx("Tu plan del mes", "Your plan for the month"),
                    tx("Cuánto podés repartir y cómo", "How much you can split, and how"), nav, "strategy")
                PlanRow(plan.allows(Feature.DEBTS), PlanTier.FREE, Icons.Rounded.CreditCard, tx("Deudas", "Debts"),
                    tx("Saldos, cuotas y pagos", "Balances, payments"), nav, "debts")
                // UX-7: the declared income and essential expenses, every plan (with Metas y ahorros → Tus ahorros it replaces Perfil → Situación).
                PlanRow(true, PlanTier.FREE, Icons.Rounded.Payments, tx("Ingresos y base", "Income and base"),
                    tx("Ingreso y gastos esenciales", "Income and essential expenses"), nav, "incomeBase")
                PlanRow(plan.allows(Feature.STRATEGY_VIP), PlanTier.VIP, Icons.Rounded.Shield, tx("Salvavidas", "Emergency fund"),
                    tx("Cuántos meses de obligaciones te cubre", "How many months of obligations it covers"), nav, "salvavidas")
                PlanRow(plan.allows(Feature.STRATEGY_BASIC), PlanTier.BASIC, Icons.Rounded.PieChart, tx("Distribución de dinero", "Money distribution"),
                    tx("Cómo repartir tu sobrante", "How to split your surplus"), nav, "distribution")
            }
        }
    }
}

@Composable
private fun PlanRow(available: Boolean, minimum: PlanTier, icon: androidx.compose.ui.graphics.vector.ImageVector, title: String, subtitle: String, nav: Navigator, route: String) {
    if (available) NavRow(icon, title, subtitle) { nav.open(route) }
    else NavRow(icon, title, if (minimum == PlanTier.VIP) tx("Disponible desde VIP", "Available from VIP") else tx("Disponible desde Basic", "Available from Basic"),
        badge = if (minimum == PlanTier.VIP) "VIP" else "Basic") { nav.open("plans") }
}

/** E2–E5 — debts: list with progress, create, edit (Basic+), payment, delete. */
@Composable
fun DebtsScreen(model: AppModel, nav: Navigator) {
    val profile by model.profile.collectAsStateWithLifecycle()
    val advanced = (profile?.planTier ?: PlanTier.FREE).allows(Feature.STRATEGY_BASIC)
    val debts = rememberLoad(model) { model.api.debts() }
    var editing by remember { mutableStateOf<Debt?>(null) }
    var creating by remember { mutableStateOf(false) }
    var paying by remember { mutableStateOf<Debt?>(null) }
    var deleting by remember { mutableStateOf<Debt?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) { model.recordScreen("debts_opened", "debts") }
    DetailScaffold(tx("Deudas", "Debts"), nav::back, actions = {
        IconButton({ creating = true }, modifier = Modifier.heightIn(min = 48.dp)) { Icon(Icons.Rounded.Add, contentDescription = tx("Agregar deuda", "Add debt")) }
    }) {
        LoadContent(debts) { list ->
            if (list.isEmpty()) {
                EmptyState(Icons.Rounded.CreditCard, tx("Sin deudas registradas", "No debts yet"),
                    tx("Registrá tarjetas y préstamos para ver cuánto debés y cuándo terminás.", "Add cards and loans to see what you owe and when you’ll be done.")) {
                    DincrPrimaryButton(tx("Agregar deuda", "Add debt"), { creating = true })
                }
            } else {
                DincrCard {
                    Column {
                        // A total only when every debt has the figure: an unknown one is never added as 0.
                        AmountLine(tx("Total pendiente", "Total outstanding"), Debt.knownSum(list.map { it.remainingAmount }), emphasize = true)
                        AmountLine(tx("Cuotas del mes", "Monthly payments"), Debt.knownSum(list.map { it.monthlyPayment }))
                    }
                }
                list.forEach { debt -> DebtCard(debt, advanced, onEdit = { editing = debt }, onPay = { paying = debt }, onDelete = { deleting = debt }) }
            }
        }
    }
    if (creating || editing != null) DebtForm(model, editing, advanced, onDismiss = { creating = false; editing = null }) {
        creating = false; editing = null; debts.reload(); model.showNotice(it)
    }
    paying?.let { debt ->
        AmountDialog(tx("Registrar pago", "Record payment"), tx("Pendiente: ${Dincr.money.format(debt.remainingAmount ?: BigDecimal.ZERO)}. Un pago mayor se ajusta al saldo.", "Outstanding: ${Dincr.money.format(debt.remainingAmount ?: BigDecimal.ZERO)}. A larger payment is capped at the balance."),
            tx("Registrar", "Record"), onDismiss = { paying = null }) { amount, key ->
            model.load(tx("No pudimos registrar el pago.", "We couldn’t record the payment.")) { model.api.payDebt(debt.id, amount, key) }.fold(
                { paying = null; debts.reload(); model.showNotice(tx("Pago registrado", "Payment recorded")); null },
                { if (it is AuthException.SignedOut) null else it.message })
        }
    }
    deleting?.let { debt ->
        ConfirmDialog(tx("¿Eliminar «${debt.name.orEmpty()}»?", "Delete “${debt.name.orEmpty()}”?"), tx("Se borra la deuda y su historial de pagos en DINCR. No se puede deshacer.", "The debt and its payment history in DINCR are removed. This can’t be undone."),
            tx("Eliminar", "Delete"), busy = busy, onDismiss = { deleting = null }, onConfirm = {
                busy = true
                scope.launch {
                    val result = model.load(tx("No pudimos eliminarla.", "We couldn’t delete it.")) { model.api.deleteDebt(debt.id) }
                    busy = false; deleting = null
                    if (result.isSuccess || (result.exceptionOrNull() as? ApiError)?.kind == ApiError.Kind.NOT_FOUND) { debts.reload(); model.showNotice(tx("Deuda eliminada", "Debt deleted")) }
                    else result.exceptionOrNull()?.takeIf { it !is AuthException.SignedOut }?.message?.let(model::showNotice)
                }
            })
    }
}

@Composable
private fun DebtCard(debt: Debt, advanced: Boolean, onEdit: () -> Unit, onPay: () -> Unit, onDelete: () -> Unit) {
    DincrCard {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(debt.name.orEmpty(), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
                    Caption(debtTypeLabel(debt.debtType) + (debt.interestRate?.let { " · " + tx("${it.stripTrailingZeros().toPlainString()} % anual", "${it.stripTrailingZeros().toPlainString()} % a year") } ?: ""))
                }
                MoneyText(debt.remainingAmount)
            }
            // The backend sends 0 % when the original amount is unknown: progress only from a known one.
            debt.knownProgressPercent?.let { ProgressLine(it / 100.0, tx("${it.toInt()} % pagado", "${it.toInt()} % paid")) }
            debt.monthlyPayment?.let { AmountLine(tx("Cuota mensual", "Monthly payment"), it) }
            debt.nextPaymentDate?.let { InfoLine(tx("Próximo pago", "Next payment"), dateLabel(it)) }
            Row(horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                // A payment on a paid-off debt would record a zero payment: not offered.
                if ((debt.remainingAmount ?: BigDecimal.ZERO).signum() > 0) TextButton(onPay, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Registrar pago", "Record payment"), color = Dincr.colors.tint) }
                if (advanced) TextButton(onEdit, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Editar", "Edit"), color = Dincr.colors.tint) }
                TextButton(onDelete, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Eliminar", "Delete"), color = Dincr.colors.negative) }
            }
        }
    }
}

fun debtTypeLabel(type: String?) = when (type) {
    "credit_card" -> tx("Tarjeta de crédito", "Credit card")
    "loan" -> tx("Préstamo", "Loan")
    "tasa_cero" -> tx("Tasa cero", "Zero interest")
    else -> tx("Otra deuda", "Other debt")
}

/** E3 — create (all plans) or edit (Basic+). Empty optional fields are sent as unknown, never 0. */
@Composable
private fun DebtForm(model: AppModel, debt: Debt?, advanced: Boolean, onDismiss: () -> Unit, onSaved: (String) -> Unit) {
    val format = Dincr.money
    val separators = format.separators
    fun text(value: BigDecimal?) = value?.let(format::inputText).orEmpty()
    var name by remember { mutableStateOf(debt?.name.orEmpty()) }
    var type by remember { mutableStateOf(debt?.debtType ?: "credit_card") }
    var remaining by remember { mutableStateOf(text(debt?.remainingAmount)) }
    var total by remember { mutableStateOf(text(debt?.totalAmount)) }
    var monthly by remember { mutableStateOf(text(debt?.monthlyPayment)) }
    // An unknown rate starts empty (never "0"); the starting text tells whether the user touched it.
    val initialInterest = remember { debt?.rateForEditing?.let(format::inputText).orEmpty() }
    var interest by remember { mutableStateOf(initialInterest) }
    var term by remember { mutableStateOf(debt?.termMonths?.toString().orEmpty()) }
    var day by remember { mutableStateOf(debt?.paymentDay?.toString().orEmpty()) }
    var next by remember { mutableStateOf(debt?.nextPaymentDate?.let { runCatching { LocalDate.parse(it) }.getOrNull() }) }
    var errors by remember { mutableStateOf(mapOf<String, String>()) }
    var error by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    val key = remember { IdempotencyKey.new() }
    val scope = rememberCoroutineScope()
    val example = amountExample()
    FormSheet(if (debt == null) tx("Nueva deuda", "New debt") else tx("Editar deuda", "Edit debt"), saving, error, tx("Guardar", "Save"), onDismiss = onDismiss, onPrimary = {
        val found = mutableMapOf<String, String>()
        if (name.isBlank()) found["name"] = tx("Escribí un nombre.", "Enter a name.")
        val remainingValue = AmountInput.parseZeroOrMore(remaining, separators).also { if (it == null) found["remaining"] = tx("Escribí el saldo, por ejemplo $example.", "Enter the balance, for example $example.") }
        fun optionalMoney(field: String, value: String) = if (value.isBlank()) null else AmountInput.parseZeroOrMore(value, separators).also { if (it == null) found[field] = tx("Monto no válido.", "Not a valid amount.") }
        val totalValue = optionalMoney("total", total)
        val monthlyValue = optionalMoney("monthly", monthly)
        val interestValue = if (!advanced || interest.isBlank()) null else InterestRateInput.parse(interest, separators).also { if (it == null) found["interest"] = tx("Tasa entre 0 y 9999,9999.", "Rate between 0 and 9999.9999.") }
        val termValue = if (!advanced || term.isBlank()) null else WholeNumberInput.parse(term, 1..600).also { if (it == null) found["term"] = tx("Entre 1 y 600 meses.", "1 to 600 months.") }
        val dayValue = if (!advanced || day.isBlank()) null else WholeNumberInput.parse(day, 1..31).also { if (it == null) found["day"] = tx("Entre 1 y 31.", "1 to 31.") }
        if (totalValue != null && remainingValue != null && totalValue < remainingValue) found["total"] = tx("No puede ser menor que el saldo pendiente.", "Can’t be less than the balance.")
        errors = found
        if (found.isNotEmpty() || remainingValue == null) return@FormSheet
        saving = true; error = null
        val request = DebtRequest(name.trim(), if (advanced) type else (debt?.debtType ?: "other"), remainingValue, totalValue, monthlyValue,
            if (advanced) interestValue else debt?.interestRate, if (advanced) termValue else debt?.termMonths, if (advanced) dayValue else debt?.paymentDay,
            if (advanced) next?.toString() else debt?.nextPaymentDate,
            interestRateConfirmed = if (debt != null && advanced) DebtRequest.rateConfirmed(initialInterest, interest) else null)
        scope.launch {
            model.load(tx("No pudimos guardar la deuda.", "We couldn’t save the debt.")) {
                if (debt == null) model.api.createDebt(request, key) else model.api.updateDebt(debt.id, request, key)
            }.onSuccess { onSaved(if (debt == null) tx("Deuda agregada", "Debt added") else tx("Deuda actualizada", "Debt updated")) }
                .onFailure { if (it !is AuthException.SignedOut) error = it.message }
            saving = false
        }
    }) {
        FormField(tx("Nombre", "Name"), name, { name = it }, errors["name"])
        if (advanced) ChoiceChips(listOf("credit_card" to tx("Tarjeta", "Card"), "loan" to tx("Préstamo", "Loan"), "other" to tx("Otra", "Other")), type, { type = it }, tx("Tipo", "Type"))
        MoneyField(tx("Saldo pendiente", "Outstanding balance"), remaining, { remaining = it }, errors["remaining"])
        MoneyField(tx("Monto original (opcional)", "Original amount (optional)"), total, { total = it }, errors["total"])
        MoneyField(tx("Cuota mensual (opcional)", "Monthly payment (optional)"), monthly, { monthly = it }, errors["monthly"])
        if (advanced) {
            FormField(tx("Tasa de interés anual % (opcional)", "Annual interest % (optional)"), interest, { interest = it }, errors["interest"], KeyboardType.Decimal)
            FormField(tx("Plazo en meses (opcional)", "Term in months (optional)"), term, { term = it }, errors["term"], KeyboardType.Number)
            FormField(tx("Día de pago (opcional)", "Payment day (optional)"), day, { day = it }, errors["day"], KeyboardType.Number)
            DateField(tx("Próximo pago", "Next payment"), next, { next = it }, allowClear = true)
        }
    }
}
