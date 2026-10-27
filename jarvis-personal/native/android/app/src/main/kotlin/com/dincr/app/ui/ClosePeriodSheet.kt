package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.ConversionPreview
import com.dincr.data.ExchangeRateInput
import com.dincr.data.IdempotencyKey
import com.dincr.data.PendingClose
import com.dincr.data.PendingConversion
import com.dincr.design.Dincr
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.TabularNums
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal
import kotlinx.coroutines.launch

/** How a close is named: "Corte del 21 oct · Tarjeta ••5678" or "Octubre 2026". iOS: `PendingPeriodLabel`. */
fun pendingPeriodTitle(period: PendingConversion.Period): String {
    if (period.isCard) {
        val card = listOfNotNull(period.accountName, period.accountLast4?.let { "••$it" }).joinToString(" ")
        val cut = tx("Corte del ${dayLabel(period.end)}", "Cut of ${dayLabel(period.end)}")
        return if (card.isEmpty()) cut else "$cut · $card"
    }
    val month = runCatching { java.time.YearMonth.parse(period.start.take(7)) }.getOrNull() ?: return period.start.take(7)
    val formatter = java.time.format.DateTimeFormatter.ofPattern("LLLL yyyy", java.util.Locale(tx("es", "en"), tx("CR", "US")))
    return month.format(formatter).replaceFirstChar { it.titlecase() }
}

/** The header of one close in Movimientos: its name, totals, and the conversion once it has ended. */
@Composable
fun PendingHeader(period: PendingConversion.Period?, totals: List<PendingConversion.Total>, onClose: (PendingConversion.Period) -> Unit) {
    Column(Modifier.widthIn(max = 600.dp).fillMaxWidth().padding(top = DincrSpacing.s5, bottom = DincrSpacing.s1)) {
        val title = period?.let { tx("En dólares · ${pendingPeriodTitle(it)}", "In dollars · ${pendingPeriodTitle(it)}") }
            ?: tx("En dólares · se convierten al cierre", "In dollars · converted at the close")
        Text(title, style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2, modifier = Modifier.semantics { heading() })
        totals.forEach { total ->
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("movements.pending.total.${total.currency}"), verticalAlignment = Alignment.CenterVertically) {
                Text(tx("Total por convertir", "Total to convert"), style = MaterialTheme.typography.titleSmall, color = Dincr.colors.text, modifier = Modifier.weight(1f))
                Text(Dincr.money.copy(currency = total.currency).format(total.amount), style = MaterialTheme.typography.titleSmall.merge(TabularNums), color = Dincr.colors.text)
            }
        }
        when {
            period == null -> Text(tx("No suman en colones hasta el cierre: el corte de la tarjeta, o fin de mes sin tarjeta.",
                "They don’t add up in colones until the close: the card’s statement cut, or month end without a card."),
                style = MaterialTheme.typography.bodySmall, color = Dincr.colors.textMuted)
            period.closable -> TextButton({ onClose(period) }, Modifier.heightIn(min = 48.dp).testTag("movements.pending.close.${period.key}")) {
                Text(tx("Convertir a colones", "Convert to colones"), color = Dincr.colors.tint)
            }
            else -> Text(tx("Se convierte desde el ${dayLabel(period.end)}, con un solo tipo de cambio.", "It converts from ${dayLabel(period.end)}, with one rate."),
                style = MaterialTheme.typography.bodySmall, color = Dincr.colors.textMuted)
        }
        if (period?.cutDayMissing == true) {
            Text(tx("Una tarjeta no tiene día de corte: se cierra a fin de mes. Declaralo en Cuentas para cerrarla por su corte.",
                "A card has no cut day: it closes at month end. Declare it in Accounts to close it by its cut."),
                style = MaterialTheme.typography.bodySmall, color = Dincr.colors.textMuted)
        }
    }
}

/**
 * The close (3d): one rate converts every dollar expense waiting in one period. The user types their own
 * rate — DINCR never looks one up — and sees the colones total before confirming. iOS: `ClosePeriodSheet`.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ClosePeriodSheet(model: AppModel, period: PendingConversion.Period, latestRate: BigDecimal?, onDismiss: () -> Unit, onClosed: (String) -> Unit) {
    val format = Dincr.money
    val profile by model.profile.collectAsStateWithLifecycle()
    val base = (profile?.baseCurrency ?: "CRC").uppercase()
    var rateText by remember { mutableStateOf(latestRate?.let(format::inputText).orEmpty()) }
    var rateError by remember { mutableStateOf<String?>(null) }
    var saveError by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    var submission by remember { mutableStateOf<Pair<PendingClose, String>?>(null) }
    val scope = rememberCoroutineScope()
    val rate = ExchangeRateInput.parse(rateText, format.separators)
    val preview = rate?.let { r ->
        val parts = period.totals.map { ConversionPreview.baseAmount(it.amount, it.currency, base, r) }
        if (parts.all { it != null }) parts.filterNotNull().fold(BigDecimal.ZERO, BigDecimal::add) else null
    }

    fun close() {
        if (saving) return
        val chosen = rate ?: run { rateError = tx("Escribí cuántos colones vale 1 dólar (mayor que cero).", "Enter how many colones 1 dollar is worth (above zero)."); return }
        val body = PendingClose(period.key, chosen)
        val key = submission?.takeIf { it.first == body }?.second ?: IdempotencyKey.new()
        submission = body to key
        saving = true; saveError = null
        scope.launch {
            val result = model.load(tx("No pudimos convertir. Revisá tu conexión e intentá de nuevo.", "We couldn’t convert. Check your connection and try again.")) {
                model.api.closePending(body, key)
            }
            saving = false
            result.onSuccess { onClosed(tx("Convertidos ${it.converted} gasto(s): ${format.format(it.amount)}", "Converted ${it.converted} expense(s): ${format.format(it.amount)}")) }
                .onFailure { saveError = it.message }
        }
    }

    ModalBottomSheet(onDismissRequest = { if (!saving) onDismiss() }, sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true), containerColor = Dincr.colors.surface) {
        Column(Modifier.fillMaxWidth().imePadding().navigationBarsPadding().padding(horizontal = DincrSpacing.s4, vertical = DincrSpacing.s2),
            verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
            Text(tx("Convertir a colones", "Convert to colones"), style = MaterialTheme.typography.headlineSmall, color = Dincr.colors.text)
            Text(pendingPeriodTitle(period), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
            period.totals.forEach { total ->
                Text(tx("${format.copy(currency = total.currency).format(total.amount)} en ${total.count} gasto(s)",
                    "${format.copy(currency = total.currency).format(total.amount)} in ${total.count} expense(s)"),
                    style = MaterialTheme.typography.bodyLarge.merge(TabularNums), color = Dincr.colors.text2)
            }
            OutlinedTextField(rateText, { rateText = it; rateError = null }, label = { Text(tx("Tipo de cambio (₡ por US\$1)", "Exchange rate (₡ per US\$1)")) },
                singleLine = true, isError = rateError != null,
                supportingText = { Text(rateError ?: tx("Usá el tipo de cambio de tu estado de cuenta. DINCR no lo inventa.", "Use your statement’s rate. DINCR never makes one up.")) },
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), modifier = Modifier.fillMaxWidth().testTag("close.rate"))
            preview?.let {
                Text(tx("Se registran ${format.format(it)} en total.", "${format.format(it)} are recorded in total."),
                    style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2, modifier = Modifier.testTag("close.preview"))
            }
            saveError?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.negative) }
            DincrPrimaryButton(tx("Convertir", "Convert"), { close() }, modifier = Modifier.fillMaxWidth().testTag("close.save"), enabled = !saving)
        }
    }
}
