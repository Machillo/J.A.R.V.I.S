package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.People
import androidx.compose.material3.AlertDialog
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
import androidx.compose.ui.unit.dp
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AmountInput
import com.dincr.data.AuthException
import com.dincr.data.Receivable
import com.dincr.data.ReceivableEntryRequest
import com.dincr.data.ReceivablePaymentRequest
import com.dincr.data.ReceivablesReport
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.EmptyState
import com.dincr.design.MoneyText
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal
import java.time.LocalDate
import kotlinx.coroutines.launch

/**
 * JARVIS → Control de dinero (Owner only): the historical "Cuentas por cobrar". Who owes the Owner
 * money in the current card cycle, how much, and each charge and payment; "Registrar pago" and
 * "Nuevo cobro" are explicit Owner commands, sent once (the backend does not deduplicate them).
 * Opening the screen only reads. Every amount is the backend's. iOS: `MoneyControlView`.
 */
@Composable
fun MoneyControlScreen(model: AppModel, nav: Navigator) {
    val report = rememberLoad(model) { model.api.receivables() }
    var paying by remember { mutableStateOf<Receivable?>(null) }
    var adding by remember { mutableStateOf(false) }
    DetailScaffold(tx("Control de dinero", "Money control"), nav::back, actions = {
        IconButton({ adding = true }, modifier = Modifier.heightIn(min = 48.dp).testTag("money.add")) {
            Icon(Icons.Rounded.Add, contentDescription = tx("Nuevo cobro", "New collection"))
        }
    }) {
        LoadContent(report) { data -> MoneyControlContent(data, pay = { paying = it }) }
    }
    paying?.let { receivable ->
        val due = Dincr.money.format(receivable.currentAmountDue ?: BigDecimal.ZERO)
        AmountDialog(tx("Pago de ${receivable.personName.orEmpty()}", "Payment from ${receivable.personName.orEmpty()}"),
            tx("Debe: $due.", "Owes: $due."), tx("Registrar", "Record"), onDismiss = { paying = null }) { amount, _ ->
            model.load(tx("No pudimos registrarlo. Revisá la lista antes de intentar de nuevo.", "We couldn’t record it. Check the list before trying again.")) {
                model.api.recordReceivablePayment(receivable.id, ReceivablePaymentRequest(amount, paymentDate = LocalDate.now().toString()))
            }.fold(
                { paying = null; report.reload(); model.showNotice(tx("Pago registrado", "Payment recorded")); null },
                { if (it is AuthException.SignedOut) null else it.message })
        }
    }
    if (adding) ReceivableEntryDialog(model, onDismiss = { adding = false }) {
        adding = false; report.reload(); model.showNotice(tx("Cobro registrado", "Collection recorded"))
    }
}

@Composable
private fun MoneyControlContent(report: ReceivablesReport, pay: (Receivable) -> Unit) {
    DincrCard(Modifier.testTag("money.summary")) {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
            Caption(tx("Te deben", "Owed to you"))
            MoneyText(report.summary?.totalPending, style = MaterialTheme.typography.headlineMedium)
            report.summary?.countOpen?.let { open ->
                Caption(if (open == 1) tx("1 persona con saldo pendiente", "1 person with an amount due")
                else tx("$open personas con saldo pendiente", "$open people with an amount due"))
            }
            val start = report.cycle?.start
            val end = report.cycle?.end
            if (start != null && end != null) Caption(tx("Ciclo de tarjeta: ${dateLabel(start)} – ${dateLabel(end)}", "Card cycle: ${dateLabel(start)} – ${dateLabel(end)}"))
        }
    }
    if (report.items.isEmpty()) {
        EmptyState(Icons.Rounded.People, tx("Nadie te debe dinero", "No one owes you money"),
            tx("Con «+» registrás lo que alguien te debe.", "Use “+” to record what someone owes you."))
    }
    report.items.forEach { ReceivableCard(it, pay = { pay(it) }) }
}

@Composable
private fun ReceivableCard(receivable: Receivable, pay: () -> Unit) {
    var showsHistory by remember { mutableStateOf(false) }
    DincrCard(Modifier.testTag("money.person.${receivable.id}")) {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(receivable.personName ?: tx("Persona", "Person"), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
                    Caption(statusLabel(receivable.status) + if (receivable.isAuto) tx(" · Tarjeta adicional", " · Additional card") else "")
                }
                MoneyText(receivable.currentAmountDue)
            }
            receivable.carriedPending?.takeIf { it.signum() != 0 }?.let { AmountLine(tx("De ciclos anteriores", "From earlier cycles"), it) }
            receivable.cycleCharges?.takeIf { it.signum() > 0 }?.let { AmountLine(tx("Cargos de este ciclo", "Charges this cycle"), it) }
            receivable.cyclePayments?.takeIf { it.signum() > 0 }?.let { AmountLine(tx("Pagos de este ciclo", "Payments this cycle"), it) }
            Row(horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                if (receivable.canRecordPayment) TextButton(pay, modifier = Modifier.heightIn(min = 48.dp).testTag("money.pay.${receivable.id}")) {
                    Text(tx("Registrar pago", "Record payment"), color = Dincr.colors.tint)
                }
                if (receivable.history.isNotEmpty()) TextButton({ showsHistory = !showsHistory }, modifier = Modifier.heightIn(min = 48.dp).testTag("money.history.${receivable.id}")) {
                    Text(if (showsHistory) tx("Ocultar movimientos", "Hide entries") else tx("Ver movimientos", "Show entries"), color = Dincr.colors.tint)
                }
            }
            if (showsHistory) receivable.history.forEach { entry ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(if (entry.isPayment) tx("Pago", "Payment") else tx("Cargo", "Charge"), style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text)
                        Caption(listOfNotNull(entry.entryDate?.let { dateLabel(it) }, entry.description?.takeIf { it.isNotBlank() }).joinToString(" · "))
                    }
                    MoneyText(entry.amount?.let { if (entry.isPayment) it.negate() else it })
                }
            }
        }
    }
}

private fun statusLabel(status: Receivable.Status): String = when (status) {
    Receivable.Status.PENDING -> tx("Pendiente", "Pending")
    Receivable.Status.PARTIAL -> tx("Pagó una parte", "Partly paid")
    Receivable.Status.COMPLETED -> tx("Al día", "Settled")
    Receivable.Status.CREDIT -> tx("Tiene saldo a favor", "Has credit")
    Receivable.Status.UNKNOWN -> tx("Sin estado", "No status")
}

private fun kindLabel(kind: String): String = when (kind) {
    "purchase" -> tx("Compra", "Purchase")
    "loan" -> tx("Préstamo", "Loan")
    "transfer" -> tx("Transferencia", "Transfer")
    "cash" -> tx("Efectivo", "Cash")
    else -> tx("Otro", "Other")
}

/** "Nuevo cobro": money someone now owes the Owner. Sent once: disabled while it is sent, never retried on its own. */
@Composable
private fun ReceivableEntryDialog(model: AppModel, onDismiss: () -> Unit, onSaved: () -> Unit) {
    var person by remember { mutableStateOf("") }
    var amount by remember { mutableStateOf("") }
    var detail by remember { mutableStateOf("") }
    var kind by remember { mutableStateOf("purchase") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val separators = Dincr.money.separators
    val example = amountExample()
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text(tx("Nuevo cobro", "New collection")) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                FormField(tx("Quién te debe", "Who owes you"), person, { person = it; error = null }, modifier = Modifier.testTag("money.entry.person"))
                MoneyField(tx("Monto", "Amount"), amount, { amount = it; error = null }, modifier = Modifier.testTag("money.entry.amount"))
                ChoiceChips(ReceivableEntryRequest.kinds.map { it to kindLabel(it) }, kind, { kind = it }, tx("Tipo", "Kind"))
                FormField(tx("Detalle (opcional)", "Detail (optional)"), detail, { detail = it }, modifier = Modifier.testTag("money.entry.detail"))
                error?.let { Text(it, color = Dincr.colors.negative, style = MaterialTheme.typography.bodySmall) }
            }
        },
        confirmButton = {
            TextButton(enabled = !busy, modifier = Modifier.testTag("money.entry.save"), onClick = {
                val name = person.trim()
                val value = AmountInput.parse(amount, separators)
                when {
                    name.isEmpty() -> error = tx("Escribí quién te debe.", "Enter who owes you.")
                    value == null -> error = tx("Escribí un monto mayor que cero, por ejemplo $example.", "Enter an amount above zero, for example $example.")
                    else -> {
                        busy = true
                        scope.launch {
                            model.load(tx("No pudimos guardarlo. Revisá la lista antes de intentar de nuevo.", "We couldn’t save it. Check the list before trying again.")) {
                                model.api.addReceivableEntry(ReceivableEntryRequest(name, value, detail.trim(), kind))
                            }.fold({ onSaved() }, { if (it !is AuthException.SignedOut) error = it.message })
                            busy = false
                        }
                    }
                }
            }) { Text(tx("Guardar", "Save")) }
        },
        dismissButton = { TextButton(onDismiss, enabled = !busy) { Text(tx("Cancelar", "Cancel")) } },
    )
}
