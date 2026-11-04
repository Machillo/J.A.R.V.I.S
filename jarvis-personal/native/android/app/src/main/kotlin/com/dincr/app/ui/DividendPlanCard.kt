package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AuthException
import com.dincr.data.CorrectionInput
import com.dincr.data.DividendPlan
import com.dincr.data.DividendPlanUpdate
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal
import kotlinx.coroutines.launch

/**
 * JARVIS → Patrimonio → Inversiones: "Plan de dividendos". Says how much capital the monthly goal
 * needs with the stocks the Owner picked, and what to buy this month only when the plan allows it
 * (no debt at 10% a year or more, 3 months of Salvavidas). Opening it only reads. The app has no
 * market data: the yield is what the Owner typed. iOS: `DividendPlanCard`.
 */
@Composable
fun DividendPlanCard(model: AppModel) {
    val data = rememberLoad(model, fallback = tx("No pudimos cargar tu plan de dividendos.", "We couldn’t load your dividend plan.")) { model.api.dividendPlan() }
    var editing by remember { mutableStateOf<DividendPlan?>(null) }
    LoadContent(data) { plan ->
        DincrCard(Modifier.testTag("wealth.dividends")) {
            Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
                Caption(tx("Plan de dividendos", "Dividend plan"))
                when {
                    !plan.isConfigured -> Text(tx("Elegí tus acciones y tu meta para saber cuánto necesitás.", "Pick your stocks and your goal to see how much you need."),
                        style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text)
                    !plan.result.ready -> Text(tx("Falta el dividendo anual de tus acciones para poder calcular.", "Your stocks’ yearly dividend is missing, so it can’t be calculated yet."),
                        style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text, modifier = Modifier.testTag("wealth.dividends.incomplete"))
                    else -> Figures(plan)
                }
                TextButton({ editing = plan }, modifier = Modifier.heightIn(min = 48.dp).testTag("wealth.dividends.edit")) {
                    Text(if (plan.isConfigured) tx("Editar", "Edit") else tx("Configurar", "Set up"), color = Dincr.colors.tint)
                }
            }
        }
    }
    editing?.let { plan ->
        DividendPlanDialog(model, plan, onDismiss = { editing = null }) { editing = null; data.reload() }
    }
}

@Composable
private fun Figures(plan: DividendPlan) {
    val result = plan.result
    AmountLine(tx("Tu meta al mes", "Your monthly goal"), plan.config.goalMonthlyUsd, currency = "USD")
    AmountLine(tx("Capital que necesitás", "Capital you need"), result.capitalNeededUsd, emphasize = true, currency = "USD")
    AmountLine(tx("Tenés en estas acciones", "You hold in these stocks"), result.currentValueUsd, currency = "USD")
    AmountLine(tx("Te falta", "Still missing"), result.missingUsd, currency = "USD")
    AmountLine(tx("Hoy te daría al mes", "It would pay you monthly today"), result.netMonthlyDividendNowUsd, currency = "USD")
    if (result.monthlyNeeded.isNotEmpty()) {
        Caption(tx("Cuánto comprar al mes para llegar", "How much to buy monthly to get there"))
        result.monthlyNeeded.forEach { AmountLine(tx("En ${it.years} años", "In ${it.years} years"), it.amountUsd, currency = "USD") }
    }
    pace(result.monthsToGoal, plan.config.monthlyAmountUsd)?.let {
        Text(it, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text, modifier = Modifier.testTag("wealth.dividends.pace"))
    }
    if (plan.gate.open) {
        if (result.buyThisMonth.isNotEmpty()) {
            Caption(tx("Este mes comprá", "This month, buy"))
            result.buyThisMonth.forEach { AmountLine(it.symbol, it.amountUsd, currency = "USD") }
        }
    } else {
        Column(Modifier.testTag("wealth.dividends.gate"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
            Text(tx("Todavía no te toca comprar más", "It’s not time to buy more yet"),
                style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold), color = Dincr.colors.warning)
            plan.gate.blockers.forEach { Text(blocker(it.code), style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text) }
        }
    }
    Caption(tx("Es un cálculo con el dividendo que escribiste, después de la retención, y con dividendos reinvertidos. Supone que el precio y el dividendo no cambian; pueden cambiar. No es asesoría de inversión.",
        "It’s a calculation with the dividend you typed, after withholding, with dividends reinvested. It assumes price and dividend stay the same; they can change. This isn’t investment advice."))
}

private fun pace(months: Int?, amount: BigDecimal?): String? {
    if (months == null) return null
    if (months == 0) return tx("Ya llegaste a tu meta.", "You’ve reached your goal.")
    val years = months / 12
    val rest = months % 12
    val time = when {
        years == 0 -> tx("$rest meses", "$rest months")
        rest == 0 -> tx("$years años", "$years years")
        else -> tx("$years años y $rest meses", "$years years and $rest months")
    }
    return if ((amount ?: BigDecimal.ZERO) > BigDecimal.ZERO) tx("Con tu aporte mensual llegás en $time.", "With your monthly amount you get there in $time.")
    else tx("Sin aportar más llegás en $time.", "Without adding more you get there in $time.")
}

private fun blocker(code: String): String = when (code) {
    "expensive_debt" -> tx("Tenés deuda con tasa anual de 10% o más.", "You have debt at 10% a year or more.")
    "debt_rate_unknown" -> tx("Falta la tasa de interés de una deuda.", "A debt’s interest rate is missing.")
    "salvavidas_short" -> tx("El Salvavidas todavía no cubre 3 meses.", "The emergency fund doesn’t cover 3 months yet.")
    "salvavidas_unknown" -> tx("Falta el saldo o el costo mensual del Salvavidas.", "The emergency fund’s balance or monthly cost is missing.")
    else -> tx("Falta un dato para decidirlo.", "Some information is missing to decide.")
}

private fun percent(text: String): BigDecimal? = text.trim().replace(',', '.').toBigDecimalOrNull()

/** The plan's form. Saving only stores the plan: it buys nothing. Sent once, never retried. */
@Composable
private fun DividendPlanDialog(model: AppModel, plan: DividendPlan, onDismiss: () -> Unit, onSaved: () -> Unit) {
    val format = Dincr.money
    val stocks = plan.config.stocks
    val first = stocks.getOrNull(0)
    val second = stocks.getOrNull(1)
    // First time: the stock already held in the portfolio, so it isn't typed again.
    var symbolA by remember { mutableStateOf(first?.symbol ?: plan.heldSymbols.firstOrNull().orEmpty()) }
    var shareA by remember { mutableStateOf(first?.sharePct?.stripTrailingZeros()?.toPlainString() ?: "100") }
    var yieldA by remember { mutableStateOf(first?.yieldPct?.stripTrailingZeros()?.toPlainString().orEmpty()) }
    var symbolB by remember { mutableStateOf(second?.symbol.orEmpty()) }
    var shareB by remember { mutableStateOf(second?.sharePct?.stripTrailingZeros()?.toPlainString().orEmpty()) }
    var yieldB by remember { mutableStateOf(second?.yieldPct?.stripTrailingZeros()?.toPlainString().orEmpty()) }
    var goal by remember { mutableStateOf(plan.config.goalMonthlyUsd?.let(format::inputText).orEmpty()) }
    var monthly by remember { mutableStateOf(plan.config.monthlyAmountUsd?.let(format::inputText).orEmpty()) }
    var withholding by remember { mutableStateOf(plan.config.withholdingPct?.stripTrailingZeros()?.toPlainString().orEmpty()) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text(tx("Plan de dividendos", "Dividend plan")) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                Caption(tx("Primera acción", "First stock"))
                FormField(tx("Símbolo", "Symbol"), symbolA, { symbolA = it; error = null }, modifier = Modifier.testTag("wealth.dividends.symbolA"))
                FormField(tx("Parte de lo que comprás (%)", "Share of what you buy (%)"), shareA, { shareA = it; error = null }, keyboard = KeyboardType.Decimal, modifier = Modifier.testTag("wealth.dividends.shareA"))
                FormField(tx("Dividendo anual (%)", "Yearly dividend (%)"), yieldA, { yieldA = it; error = null }, keyboard = KeyboardType.Decimal, modifier = Modifier.testTag("wealth.dividends.yieldA"))
                Caption(tx("Segunda acción (opcional)", "Second stock (optional)"))
                FormField(tx("Símbolo", "Symbol"), symbolB, { symbolB = it; error = null }, modifier = Modifier.testTag("wealth.dividends.symbolB"))
                FormField(tx("Parte de lo que comprás (%)", "Share of what you buy (%)"), shareB, { shareB = it; error = null }, keyboard = KeyboardType.Decimal, modifier = Modifier.testTag("wealth.dividends.shareB"))
                FormField(tx("Dividendo anual (%)", "Yearly dividend (%)"), yieldB, { yieldB = it; error = null }, keyboard = KeyboardType.Decimal, modifier = Modifier.testTag("wealth.dividends.yieldB"))
                FormField(tx("Meta de dividendos al mes (US$)", "Monthly dividend goal (US$)"), goal, { goal = it; error = null }, keyboard = KeyboardType.Decimal, modifier = Modifier.testTag("wealth.dividends.goal"))
                FormField(tx("Cuánto comprarías al mes (US$)", "How much you’d buy monthly (US$)"), monthly, { monthly = it; error = null }, keyboard = KeyboardType.Decimal, modifier = Modifier.testTag("wealth.dividends.monthly"))
                FormField(tx("Retención de impuestos (%)", "Tax withholding (%)"), withholding, { withholding = it; error = null }, keyboard = KeyboardType.Decimal, modifier = Modifier.testTag("wealth.dividends.withholding"))
                Caption(tx("El dividendo anual lo ves en tu bróker. La retención suele ser 30% en acciones de EE. UU.; confirmala con tu bróker.",
                    "You’ll find the yearly dividend at your broker. Withholding is usually 30% on US stocks; confirm it with your broker."))
                error?.let { Text(it, color = Dincr.colors.negative, style = MaterialTheme.typography.bodySmall, modifier = Modifier.testTag("wealth.dividends.error")) }
            }
        },
        confirmButton = {
            TextButton(enabled = !busy, modifier = Modifier.testTag("wealth.dividends.save"), onClick = {
                // Amounts in the user's separators ("1.000" is a thousand); 0 is a valid monthly amount.
                val goalValue = goal.takeIf { it.isNotBlank() }?.let { CorrectionInput.amount(it, format.separators) }
                val monthlyValue = monthly.takeIf { it.isNotBlank() }?.let { CorrectionInput.amountZeroOrMore(it, format.separators) }
                val rows = listOf(Triple(symbolA, shareA, yieldA), Triple(symbolB, shareB, yieldB)).filter { it.first.isNotBlank() }
                val badPercent = rows.any { (_, share, yld) -> percent(share) == null || (yld.isNotBlank() && percent(yld) == null) }
                when {
                    symbolA.isBlank() -> error = tx("Escribí el símbolo de tu acción.", "Enter your stock’s symbol.")
                    badPercent -> error = tx("Revisá los porcentajes.", "Check the percentages.")
                    (goal.isNotBlank() && goalValue == null) || (monthly.isNotBlank() && monthlyValue == null) ||
                        (withholding.isNotBlank() && percent(withholding) == null) -> error = tx("Revisá los montos.", "Check the amounts.")
                    else -> {
                        busy = true
                        val update = DividendPlanUpdate(
                            rows.map { (symbol, share, yld) -> DividendPlan.Stock(symbol.trim().uppercase(), percent(share)!!, yld.takeIf { it.isNotBlank() }?.let(::percent)) },
                            goalValue, monthlyValue, withholding.takeIf { it.isNotBlank() }?.let(::percent),
                        )
                        scope.launch {
                            model.load(tx("No pudimos guardar.", "We couldn’t save.")) { model.api.updateDividendPlan(update) }
                                .fold({ onSaved() }, { if (it !is AuthException.SignedOut) error = it.message })
                            busy = false
                        }
                    }
                }
            }) { Text(tx("Guardar", "Save"), color = Dincr.colors.tint) }
        },
        dismissButton = { TextButton({ onDismiss() }, enabled = !busy) { Text(tx("Cancelar", "Cancel"), color = Dincr.colors.tint) } },
    )
}
