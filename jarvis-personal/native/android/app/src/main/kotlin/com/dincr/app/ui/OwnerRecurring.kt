package com.dincr.app.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.MoneyFormat
import com.dincr.data.RecurringUpcoming
import com.dincr.design.Dincr
import com.dincr.design.MoneyText
import java.time.LocalDate

// The Owner's recurring automation (backend finance/recurring_automation.py): a recurring income
// recorded on its date, and the next incomes and debt installments. Shown only when `/auth/me`
// says owner; the backend refuses everyone else (403) whatever the app shows.

/** Owner-only fields of the recurring form: record the income automatically from a next date. */
@Composable
fun OwnerAutomationFields(auto: Boolean, onAuto: (Boolean) -> Unit, next: LocalDate?, onNext: (LocalDate?) -> Unit,
                          start: LocalDate?, onStart: (LocalDate?) -> Unit, error: String?) {
    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).toggleable(auto, role = Role.Switch, onValueChange = onAuto).testTag("recurring-auto-record"),
        verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(tx("Registrar en su fecha", "Record on its date"), color = Dincr.colors.text)
            Caption(tx("DINCR lo anota como ingreso una vez por fecha. No mueve dinero.", "DINCR records it as income once per date. It never moves money."))
        }
        Switch(auto, onCheckedChange = null)
    }
    if (auto) {
        DateField(tx("Próxima fecha", "Next date"), next, onNext)
        error?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Dincr.colors.negative) }
        DateField(tx("Desde (opcional)", "Since (optional)"), start, onStart, allowClear = true)
    }
}

/** The Owner's next recurring incomes and debt installments: expected ones are never shown as paid. */
@Composable
fun OwnerUpcoming(model: AppModel) {
    val upcoming = rememberLoad(model) { model.api.recurringUpcoming() }
    LoadContent(upcoming, rows = 2) { u ->
        if (u.incomes.isEmpty() && u.installments.isEmpty()) return@LoadContent
        Section(tx("Próximos ingresos y cuotas", "Upcoming income and instalments")) {
            u.incomes.forEach { UpcomingRow(it, income = true) }
            u.installments.forEach { UpcomingRow(it, income = false) }
        }
    }
}

@Composable
private fun UpcomingRow(entry: RecurringUpcoming.Entry, income: Boolean) {
    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(entry.name.orEmpty(), color = Dincr.colors.text)
            Caption(listOfNotNull(entry.dueDate, upcomingStatus(entry.status, income)).joinToString(" · "))
        }
        MoneyText(entry.amount, sign = if (income && !entry.isExpected) MoneyFormat.Sign.INCOME else MoneyFormat.Sign.NONE)
    }
}

fun upcomingStatus(status: String?, income: Boolean) = when (status) {
    "expected" -> if (income) tx("Previsto", "Expected") else tx("Pendiente", "Pending")
    "recorded" -> tx("Registrado", "Recorded")
    "already_recorded" -> tx("Ya estaba registrado", "Already recorded")
    "paid" -> tx("Cuota registrada", "Instalment recorded")
    else -> null
}
