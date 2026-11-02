package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material3.AlertDialog
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
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AmountInput
import com.dincr.data.AuthException
import com.dincr.data.Debt
import com.dincr.data.DebtAfterExtraAnswer
import com.dincr.data.DebtAfterExtraPending
import com.dincr.data.DebtSavingsReading
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.generated.DincrSpacing
import java.time.LocalDate
import kotlinx.coroutines.launch

/**
 * After an extra payment the bank may shorten the term or lower the installment, and sometimes says it
 * days later. Debts waiting for that answer ("El banco me avisa después", or a confirmed distribution)
 * are listed above the debts; "Ya me dijo" answers: installments left, the new installment, nothing
 * changed, or another day to be reminded (`POST …/after-extra`). Nothing is guessed. iOS twin:
 * `DebtAfterExtraViews.swift`.
 */
@Composable
fun WaitingForBankCard(debts: List<Debt>, waiting: Map<String, DebtAfterExtraPending>, canWrite: Boolean, answer: (Debt) -> Unit) {
    val rows = debts.filter { waiting.containsKey(it.id.toString()) }
    if (rows.isEmpty()) return
    DincrCard {
        Column(Modifier.fillMaxWidth().testTag("debts.waitingForBank"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
            Text(tx("Esperando al banco", "Waiting for the bank"), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
            Caption(tx("Abonaste extra: contanos si el banco bajó el plazo o la cuota.", "You paid extra: tell us whether the bank shortened the term or lowered the installment."))
            rows.forEach { debt ->
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(debt.name.orEmpty(), color = Dincr.colors.text)
                        waiting[debt.id.toString()]?.remindOn?.let { Caption(tx("Te avisamos el ${DebtSavingsReading.dayLabel(it)}", "We remind you on ${DebtSavingsReading.dayLabel(it)}")) }
                    }
                    if (canWrite) TextButton({ answer(debt) }, modifier = Modifier.heightIn(min = 48.dp).testTag("debts.afterExtra.${debt.id}")) {
                        Text(tx("Ya me dijo", "It told me"), color = Dincr.colors.tint)
                    }
                }
            }
        }
    }
}

/** What the bank did with the extra payment, or another day to be reminded. */
@Composable
fun AfterExtraDialog(model: AppModel, debt: Debt, onDismiss: () -> Unit, onDone: (String) -> Unit) {
    val separators = Dincr.money.separators
    var choice by remember { mutableStateOf(SHORTER) }
    var figure by remember { mutableStateOf("") }
    var day by remember { mutableStateOf(LocalDate.now().plusDays(3)) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text(tx("Tu abono extra", "Your extra payment")) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
                Text(debt.name.orEmpty(), color = Dincr.colors.text)
                ChoiceChips(listOf(SHORTER to tx("Bajó el plazo", "Shortened the term"), LOWER to tx("Bajó la cuota", "Lowered the installment"),
                    UNCHANGED to tx("Nada cambió", "Nothing changed"), LATER to tx("Todavía no sé", "I don't know yet")),
                    choice, { choice = it; figure = "" }, tx("¿Qué hizo el banco?", "What did the bank do?"))
                when (choice) {
                    SHORTER -> FormField(tx("Cuotas que te quedan", "Installments left"), figure, { figure = it }, keyboard = KeyboardType.Number,
                        modifier = Modifier.testTag("debts.afterExtra.remaining"))
                    LOWER -> MoneyField(tx("Cuota nueva", "New installment"), figure, { figure = it }, modifier = Modifier.testTag("debts.afterExtra.installment"))
                    LATER -> DateField(tx("Recordarme el", "Remind me on"), day, { picked -> picked?.let { day = it } })
                }
                error?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Dincr.colors.negative) }
            }
        },
        confirmButton = {
            TextButton(enabled = !busy, modifier = Modifier.heightIn(min = 48.dp).testTag("debts.afterExtra.save"), onClick = onClick@{
                val answer = when (choice) {
                    SHORTER -> DebtAfterExtraAnswer(remainingInstallments = figure.trim().toIntOrNull()?.takeIf { it in 1..600 }
                        ?: run { error = tx("Escribí cuántas cuotas te quedan.", "Enter how many installments are left."); return@onClick })
                    LOWER -> DebtAfterExtraAnswer(newMonthlyPayment = AmountInput.parse(figure, separators)?.takeIf { it.signum() > 0 }
                        ?: run { error = tx("Escribí la cuota nueva.", "Enter the new installment."); return@onClick })
                    LATER -> DebtAfterExtraAnswer(remindOn = day.toString())
                    else -> DebtAfterExtraAnswer(unchanged = true)
                }
                busy = true; error = null
                scope.launch {
                    model.load(tx("No pudimos guardar.", "We couldn’t save.")) { model.api.answerAfterExtra(debt.id, answer) }
                        .onSuccess { onDone(if (choice == LATER) tx("Te lo recordamos ese día", "We'll remind you that day") else tx("Deuda actualizada", "Debt updated")) }
                        .onFailure { if (it !is AuthException.SignedOut) error = it.message }
                    busy = false
                }
            }) { Text(tx("Guardar", "Save")) }
        },
        dismissButton = { TextButton(onDismiss, enabled = !busy) { Text(tx("Cancelar", "Cancel")) } },
    )
}

private const val SHORTER = "shorter_term"
private const val LOWER = "lower_installment"
private const val UNCHANGED = "unchanged"
private const val LATER = "later"
