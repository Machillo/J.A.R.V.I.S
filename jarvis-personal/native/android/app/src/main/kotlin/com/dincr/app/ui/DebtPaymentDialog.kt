package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.KeyboardType
import com.dincr.app.tx
import com.dincr.data.AmountInput
import com.dincr.data.AmountSubmission
import com.dincr.data.Debt
import com.dincr.data.DebtAfterExtra
import com.dincr.design.Dincr
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal
import kotlinx.coroutines.launch

/**
 * Registrar pago. A payment above the installment asks what the bank did with the extra: fewer
 * installments, a lower installment, or nothing. The user types the new figure from the bank; nothing
 * is guessed. Retrying the same amount reuses its idempotency key. iOS: `AmountSheet` (`.payDebt`).
 */
@Composable
fun DebtPaymentDialog(debt: Debt, onDismiss: () -> Unit, submit: suspend (BigDecimal, String, DebtAfterExtra?) -> String?) {
    val separators = Dincr.money.separators
    val submission = remember { AmountSubmission() }
    var text by remember { mutableStateOf("") }
    var bank by remember { mutableStateOf(UNCHANGED) }
    var figure by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val installment = debt.monthlyPayment?.takeIf { it.signum() > 0 }
    val extra = installment != null && (AmountInput.parse(text, separators)?.let { it > installment } == true)
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text(tx("Registrar pago", "Record payment")) },
        text = {
            Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
                val remaining = Dincr.money.format(debt.remainingAmount ?: BigDecimal.ZERO)
                Text(tx("Pendiente: $remaining. Un pago mayor se ajusta al saldo.", "Outstanding: $remaining. A larger payment is capped at the balance."), color = Dincr.colors.text2)
                MoneyField(tx("Monto", "Amount"), text, { text = it; error = null }, error, modifier = Modifier.testTag("amount.field"))
                if (extra) {
                    ChoiceChips(listOf(UNCHANGED to tx("Nada cambió", "Nothing changed"), SHORTER to tx("Bajó el plazo", "Shortened the term"),
                        LOWER to tx("Bajó la cuota", "Lowered the installment")), bank, { bank = it; figure = "" }, tx("¿Qué hizo el banco con lo extra?", "What did the bank do with the extra?"))
                    if (bank == SHORTER) FormField(tx("Cuotas que te quedan", "Installments left"), figure, { figure = it }, keyboard = KeyboardType.Number,
                        modifier = Modifier.testTag("amount.remainingInstallments"))
                    if (bank == LOWER) MoneyField(tx("Cuota nueva", "New installment"), figure, { figure = it }, modifier = Modifier.testTag("amount.newInstallment"))
                }
            }
        },
        confirmButton = {
            TextButton(enabled = !busy, modifier = Modifier.testTag("amount.save"), onClick = onClick@{
                val amount = AmountInput.parse(text, separators)
                    ?: run { error = tx("Escribí un monto mayor que cero.", "Enter an amount above zero."); return@onClick }
                val after: DebtAfterExtra? = when {
                    !extra || bank == UNCHANGED -> null
                    bank == SHORTER -> DebtAfterExtra.RemainingInstallments(figure.trim().toIntOrNull()?.takeIf { it in 1..600 }
                        ?: run { error = tx("Escribí cuántas cuotas te quedan.", "Enter how many installments are left."); return@onClick })
                    else -> DebtAfterExtra.NewMonthlyPayment(AmountInput.parse(figure, separators)?.takeIf { it.signum() > 0 }
                        ?: run { error = tx("Escribí la cuota nueva.", "Enter the new installment."); return@onClick })
                }
                busy = true
                val key = submission.keyFor(amount)
                scope.launch { error = submit(amount, key, after); busy = false }
            }) { Text(tx("Registrar", "Record")) }
        },
        dismissButton = { TextButton(onDismiss, enabled = !busy) { Text(tx("Cancelar", "Cancel")) } },
    )
}

private const val UNCHANGED = "unchanged"
private const val SHORTER = "shorter_term"
private const val LOWER = "lower_installment"
