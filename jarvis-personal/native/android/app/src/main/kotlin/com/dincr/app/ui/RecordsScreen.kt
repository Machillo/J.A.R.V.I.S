package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AccountBalance
import androidx.compose.material.icons.rounded.Event
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AuthException
import com.dincr.data.MoneyTimeline
import com.dincr.data.Reconciliation
import com.dincr.data.ReconciliationConfirmRequest
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.EmptyState
import com.dincr.design.MoneyText
import com.dincr.design.generated.DincrSpacing

/**
 * JARVIS → Registros (Owner only): the money timeline (the known incomes and obligations of the
 * next 45 days and the balance they leave) and the account reconciliation (expected against real
 * balance, and "Confirmar saldo real"). Opening it only reads. Every amount is the backend's.
 * iOS: `RecordsView`.
 */
@Composable
fun RecordsScreen(model: AppModel, nav: Navigator) {
    var tab by remember { mutableStateOf("timeline") }
    val timeline = rememberLoad(model) { model.api.moneyTimeline() }
    val reconciliation = rememberLoad(model) { model.api.reconciliation() }
    var confirming by remember { mutableStateOf<Reconciliation.Account?>(null) }
    DetailScaffold(tx("Registros", "Records"), nav::back) {
        ChoiceChips(listOf("timeline" to tx("Línea de tiempo", "Timeline"), "reconciliation" to tx("Conciliación", "Reconciliation")), tab, { tab = it })
        if (tab == "timeline") LoadContent(timeline) { TimelineContent(it) }
        else LoadContent(reconciliation) { ReconciliationContent(it, confirm = { account -> confirming = account }) }
    }
    confirming?.let { account ->
        // The balance is never guessed: an empty or invalid field is not sent.
        AmountDialog(tx("Confirmar saldo", "Confirm balance"),
            tx("Escribí el saldo que ves hoy en el banco para «${account.accountName.orEmpty()}» (${account.currency ?: "CRC"}).",
                "Enter today’s balance you see in the bank for “${account.accountName.orEmpty()}” (${account.currency ?: "CRC"})."),
            tx("Confirmar", "Confirm"), onDismiss = { confirming = null }) { amount, _ ->
            model.load(tx("No pudimos confirmarlo. Revisá la conciliación antes de intentar de nuevo.", "We couldn’t confirm it. Check the reconciliation before trying again.")) {
                model.api.confirmReconciliation(account.accountId, ReconciliationConfirmRequest(amount))
            }.fold(
                { confirming = null; reconciliation.reload(); model.showNotice(tx("Saldo confirmado", "Balance confirmed")); null },
                { if (it is AuthException.SignedOut) null else it.message })
        }
    }
}

@Composable
private fun TimelineContent(timeline: MoneyTimeline) {
    DincrCard(Modifier.testTag("records.timeline.summary")) {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
            AmountLine(tx("Disponible hoy", "Available today"), timeline.openingAvailable)
            AmountLine(tx("Al final del período", "At the end of the period"), timeline.endingAvailable)
            val start = timeline.startDate
            val end = timeline.endDate
            if (start != null && end != null) Caption("${dateLabel(start)} – ${dateLabel(end)}")
        }
    }
    if (timeline.events.isEmpty()) {
        EmptyState(Icons.Rounded.Event, tx("Nada programado", "Nothing scheduled"),
            tx("No hay ingresos ni obligaciones con fecha en este período.", "No dated incomes or obligations in this period."))
    }
    timeline.days.forEach { (date, events) ->
        DincrCard {
            Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                Caption(if (date.isEmpty()) tx("Sin fecha", "No date") else dateLabel(date))
                events.forEach { event ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(event.name ?: tx("Movimiento", "Movement"), style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text)
                            event.projectedBalance?.let { Caption(tx("Queda: ${Dincr.money.format(it)}", "Left: ${Dincr.money.format(it)}")) }
                            event.note?.let { Caption(it) }
                        }
                        MoneyText(if (event.kind == "goal") event.amount else event.impact)
                    }
                }
            }
        }
    }
    timeline.assumptions.forEach { Caption(it) }
}

@Composable
private fun ReconciliationContent(report: Reconciliation, confirm: (Reconciliation.Account) -> Unit) {
    report.summary?.let { summary ->
        DincrCard(Modifier.testTag("records.reconciliation.summary")) {
            Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
                summary.needsReview?.let { review ->
                    Text(when (review) {
                        0 -> tx("Todas tus cuentas cuadran.", "All your accounts match.")
                        1 -> tx("1 cuenta para revisar", "1 account to review")
                        else -> tx("$review cuentas para revisar", "$review accounts to review")
                    }, style = MaterialTheme.typography.titleSmall, color = Dincr.colors.text)
                }
                summary.unlinked?.takeIf { it > 0 }?.let { Caption(tx("$it movimientos sin cuenta asignada", "$it movements without an account")) }
                summary.possibleDuplicates?.takeIf { it > 0 }?.let { Caption(tx("$it posibles duplicados para revisar en Movimientos", "$it possible duplicates to review in Transactions")) }
                summary.untrackedAccounts?.takeIf { it > 0 }?.let { Caption(tx("$it cuentas sin saldo registrado no se comparan.", "$it accounts without a recorded balance aren’t compared.")) }
                report.note?.let { Caption(it) }
            }
        }
    }
    if (report.accounts.isEmpty()) {
        EmptyState(Icons.Rounded.AccountBalance, tx("No hay cuentas para conciliar", "No accounts to reconcile"),
            tx("Registrá el saldo de tus cuentas para compararlo con tus movimientos.", "Record your accounts’ balances to compare them with your movements."))
    }
    report.accounts.forEach { account ->
        DincrCard(Modifier.testTag("records.account.${account.accountId}")) {
            Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(listOfNotNull(account.accountName, account.last4?.let { "••$it" }).joinToString(" "),
                        style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text, modifier = Modifier.weight(1f))
                    Text(if (account.needsReview) tx("Revisar", "Review") else tx("Cuadra", "Matches"),
                        style = MaterialTheme.typography.bodySmall, color = if (account.needsReview) Dincr.colors.warning else Dincr.colors.positive)
                }
                AmountLine(tx("Saldo esperado", "Expected balance"), account.expectedBalance, currency = account.currency)
                AmountLine(tx("Último saldo real", "Last real balance"), account.realBalance, currency = account.currency)
                if (account.needsReview) AmountLine(tx("Diferencia", "Difference"), account.difference, currency = account.currency)
                TextButton({ confirm(account) }, modifier = Modifier.heightIn(min = 48.dp).testTag("records.confirm.${account.accountId}")) {
                    Text(tx("Confirmar saldo real", "Confirm real balance"), color = Dincr.colors.tint)
                }
            }
        }
    }
}
