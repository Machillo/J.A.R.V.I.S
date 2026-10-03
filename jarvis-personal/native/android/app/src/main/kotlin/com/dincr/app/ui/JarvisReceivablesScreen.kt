package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Groups
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.MoneyFormat
import com.dincr.data.Receivable
import com.dincr.data.ReceivablesReport
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.EmptyState
import com.dincr.design.MoneyText
import com.dincr.design.generated.DincrSpacing

/**
 * JARVIS → Control de dinero (Owner only): the cuentas por cobrar of the historical web Receivables
 * page — who owes the Owner money, what is due in the current card cycle, what carried over and the
 * cycle's movements. `GET /finance/receivables/view` is read only: opening this screen syncs nothing
 * and changes no receivable. Reached only through [JarvisSectionScreen] (Owner role); every figure is
 * the backend's and unknown shows "—". iOS twin: `OwnerReceivablesView.swift`.
 */
@Composable
fun JarvisReceivablesScreen(model: AppModel, nav: Navigator) {
    val data = rememberLoad(model, fallback = tx("No pudimos cargar tus cuentas por cobrar.", "We couldn’t load the money owed to you.")) {
        model.api.receivables()
    }
    DetailScaffold(tx("Cuentas por cobrar", "Money owed to you"), onBack = nav::back) {
        LoadContent(data) { report ->
            ReceivablesSummary(report)
            if (report.items.isEmpty()) {
                Column(Modifier.testTag("receivables.empty")) {
                    EmptyState(Icons.Rounded.Groups, tx("Nadie te debe", "Nobody owes you"),
                        tx("No hay cuentas por cobrar registradas.", "There’s no money owed to you on record."))
                }
            } else {
                report.items.forEach { ReceivableCard(it) }
            }
        }
    }
}

@Composable
private fun ReceivablesSummary(report: ReceivablesReport) {
    val summary = report.summary
    DincrCard {
        Column(Modifier.testTag("receivables.summary"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
            Text(tx("Pendiente de cobro", "Still owed to you"), style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2)
            MoneyText(summary?.totalPending, style = MaterialTheme.typography.displaySmall)
            summary?.peopleCount?.let { InfoLine(tx("Personas", "People"), it.toString()) }
            AmountLine(tx("Arrastrado de ciclos anteriores", "Carried from earlier cycles"), summary?.carriedPending)
            AmountLine(tx("Cargos del ciclo", "Cycle charges"), summary?.cycleCharges)
            AmountLine(tx("Abonos del ciclo", "Cycle payments"), summary?.cyclePayments)
            val cycle = report.cycle
            if (cycle?.start != null && cycle.end != null) {
                Caption(tx("Ciclo del ${dateLabel(cycle.start)} al ${dateLabel(cycle.end)}", "Cycle from ${dateLabel(cycle.start)} to ${dateLabel(cycle.end)}"))
            }
        }
    }
}

@Composable
private fun ReceivableCard(item: Receivable) {
    DincrCard {
        Column(Modifier.testTag("receivables.item.${item.id}"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Text(item.personName ?: "—", style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold),
                    color = Dincr.colors.text, modifier = Modifier.weight(1f))
                Text(receivableStatus(item.status), style = MaterialTheme.typography.bodySmall, color = Dincr.colors.text2)
            }
            AmountLine(tx("Por cobrar", "Owed"), item.currentAmountDue, emphasize = true)
            AmountLine(tx("Arrastrado", "Carried"), item.carriedPending)
            AmountLine(tx("Cargos del ciclo", "Cycle charges"), item.cycleCharges)
            AmountLine(tx("Abonos del ciclo", "Cycle payments"), item.cyclePayments)
            if (item.history.isNotEmpty()) {
                HorizontalDivider(color = Dincr.colors.line)
                item.history.forEach { entry ->
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(entry.description ?: if (entry.isPayment) tx("Abono", "Payment") else tx("Cargo", "Charge"),
                                style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text)
                            entry.entryDate?.let { Caption(dateLabel(it)) }
                        }
                        MoneyText(entry.amount, sign = if (entry.isPayment) MoneyFormat.Sign.INCOME else MoneyFormat.Sign.NONE,
                            style = MaterialTheme.typography.bodyLarge)
                    }
                }
            }
        }
    }
}

private fun receivableStatus(status: String?): String = when (status) {
    "pending" -> tx("Pendiente", "Pending")
    "partial" -> tx("Abonado", "Partly paid")
    "completed" -> tx("Al día", "Paid up")
    "credit" -> tx("A favor", "In credit")
    else -> "—"
}
