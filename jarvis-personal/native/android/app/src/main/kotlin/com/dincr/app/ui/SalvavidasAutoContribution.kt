package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material3.Checkbox
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
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.dincr.app.tx
import com.dincr.data.AmountInput
import com.dincr.data.SalvavidasRateInput
import com.dincr.data.Salvavidas
import com.dincr.data.SalvavidasPlanRequest
import com.dincr.data.SalvavidasUpdate
import com.dincr.design.Dincr
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.generated.DincrSpacing
import java.time.LocalDate

/**
 * Salvavidas automatic contributions (VIP and the Owner). Every figure is the backend's
 * (`auto_contribution`); the app only sends the plan the user ticked and filled. The interest rate is
 * offered to the Owner scope only; frequency names come from the shared `frequencyLabel`.
 * iOS: `SalvavidasAutoContributionViews.swift`.
 */
internal fun contributionsLabel(count: Int): String =
    if (count == 1) tx("1 aporte automático", "1 automatic contribution") else tx("$count aportes automáticos", "$count automatic contributions")

/** "₡2.500 cada semana": the one-line summary of a saved plan. */
internal fun planSummary(amount: String, frequency: String?): String = when (frequency) {
    "weekly" -> tx("$amount cada semana", "$amount every week")
    "biweekly" -> tx("$amount cada quincena", "$amount every two weeks")
    "monthly" -> tx("$amount cada mes", "$amount every month")
    else -> amount
}

/** "2,5 %" / "2.5%": the Owner's annual rate with the language's decimal mark. */
internal fun rateLabel(rate: java.math.BigDecimal): String {
    val plain = rate.stripTrailingZeros().toPlainString()
    return tx(plain.replace('.', ',') + " %", "$plain%")
}

/** What the enabled plan added under the balance: declared + contributions (+ Owner interest) = total. */
@Composable
internal fun SalvavidasPlanBreakdown(s: Salvavidas) {
    val plan = s.activePlan ?: return
    Column(Modifier.testTag("salvavidas.breakdown"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
        AmountLine(tx("Saldo declarado", "Declared balance"), s.declaredAmount ?: plan.baseAmount)
        AmountLine(contributionsLabel(plan.contributionsCount ?: 0), plan.contributionsAmount ?: java.math.BigDecimal.ZERO)
        if (s.isOwnerScope) {
            Column(Modifier.testTag("salvavidas.breakdown.interest")) {
                AmountLine(tx("Intereses estimados", "Estimated interest"), plan.estimatedInterest ?: java.math.BigDecimal.ZERO)
            }
        }
        plan.nextDate?.let { next ->
            Column(Modifier.testTag("salvavidas.breakdown.next")) { InfoLine(tx("Próximo aporte", "Next contribution"), dateLabel(next)) }
        }
    }
}

/** A checkbox row (≥ 48 dp) whose whole row toggles. */
@Composable
private fun CheckRow(label: String, checked: Boolean, enabled: Boolean, tag: String, onChange: (Boolean) -> Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag(tag).toggleable(checked, enabled = enabled, role = Role.Checkbox, onValueChange = onChange),
        verticalAlignment = Alignment.CenterVertically) {
        Checkbox(checked, onCheckedChange = null, enabled = enabled)
        Text(label, style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text, modifier = Modifier.weight(1f))
    }
}

/**
 * "Aportes automáticos": a box to tick (the plan works only when ticked), the amount, frequency, first
 * and optional last date; the balance of today while the savings are unknown (0 allowed); and, for the
 * Owner only, the annual interest rate. One PUT per tap of Guardar ([save] reports an error or null).
 */
@Composable
internal fun AutoContributionSection(s: Salvavidas, saving: Boolean, save: (SalvavidasUpdate, (String?) -> Unit) -> Unit) {
    val format = Dincr.money
    val saved = s.autoContribution
    // Re-read from the backend's answer after every save (the key changes with it).
    var enabled by remember(s) { mutableStateOf(saved?.isEnabled == true) }
    var amount by remember(s) { mutableStateOf(saved?.amount?.let(format::inputText).orEmpty()) }
    var frequency by remember(s) { mutableStateOf(saved?.frequency?.takeIf { it in Salvavidas.AutoContribution.FREQUENCIES } ?: "monthly") }
    var start by remember(s) { mutableStateOf(saved?.startDate?.let { runCatching { LocalDate.parse(it.take(10)) }.getOrNull() } ?: LocalDate.now()) }
    var end by remember(s) { mutableStateOf(saved?.endDate?.let { runCatching { LocalDate.parse(it.take(10)) }.getOrNull() }) }
    var savedToday by remember(s) { mutableStateOf("") }
    var rate by remember(s) { mutableStateOf(s.annualInterestRate?.stripTrailingZeros()?.toPlainString()?.let { if (tx("es", "en") == "es") it.replace('.', ',') else it }.orEmpty()) }
    var error by remember(s) { mutableStateOf<String?>(null) }
    // A saved, active plan is one line with "Editar"; the form opens only to change it.
    var editing by remember(s) { mutableStateOf(false) }
    val active = s.activePlan
    val showsFields = enabled || saved != null
    val asksBalance = enabled && !s.isAmountKnown

    Section(tx("Aportes automáticos", "Automatic contributions")) {
        Column(Modifier.testTag("salvavidas.auto"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
            if (active != null && !editing) {
                Text(planSummary(format.format(active.amount ?: java.math.BigDecimal.ZERO), active.frequency), style = MaterialTheme.typography.bodyLarge,
                    color = Dincr.colors.text, modifier = Modifier.testTag("salvavidas.auto.summary"))
                active.startDate?.let { InfoLine(tx("Desde", "From"), dateLabel(it)) }
                active.endDate?.let { InfoLine(tx("Hasta", "Until"), dateLabel(it)) }
                if (s.isOwnerScope) s.annualInterestRate?.let { InfoLine(tx("Interés anual", "Annual interest"), rateLabel(it)) }
                TextButton({ editing = true }, enabled = !saving, modifier = Modifier.heightIn(min = 48.dp).testTag("salvavidas.auto.edit")) {
                    Text(tx("Editar aportes", "Edit contributions"), color = Dincr.colors.tint)
                }
                return@Column
            }
            Caption(tx("Si un monto fijo entra a tu Salvavidas (por ejemplo, una transferencia automática), DINCR lo suma a tu saldo según el plan.",
                "If a fixed amount goes into your emergency fund (for example, an automatic transfer), DINCR adds it to your balance following the plan."))
            CheckRow(tx("Activar aportes automáticos", "Turn on automatic contributions"), enabled, !saving, "salvavidas.auto.enabled") { enabled = it }
            if (showsFields) {
                MoneyField(tx("Monto por aporte", "Amount per contribution"), amount, { amount = it }, modifier = Modifier.testTag("salvavidas.auto.amount"))
                ChoiceChips(Salvavidas.AutoContribution.FREQUENCIES.map { it to frequencyLabel(it) }, frequency, { frequency = it }, tx("Frecuencia", "Frequency"))
                DateField(tx("Primer aporte", "First contribution"), start, { picked -> picked?.let { start = it } })
                DateField(tx("Termina (opcional)", "Ends (optional)"), end, { end = it }, allowClear = true)
                if (asksBalance) {
                    MoneyField(tx("¿Cuánto tenés ahorrado hoy? (puede ser 0)", "How much do you have saved today? (it can be 0)"), savedToday, { savedToday = it },
                        modifier = Modifier.testTag("salvavidas.auto.current"))
                }
            }
            if (s.offersInterestRate) {
                FormField(tx("Interés anual ganado (%)", "Annual interest earned (%)"), rate, { rate = it }, keyboard = KeyboardType.Decimal,
                    supporting = tx("Estimamos los intereses con esta tasa; el banco acredita los reales.", "We estimate the interest with this rate; your bank credits the real one."),
                    modifier = Modifier.testTag("salvavidas.auto.rate"))
            }
            error?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Dincr.colors.negative, modifier = Modifier.testTag("salvavidas.auto.error")) }
            if (showsFields || s.offersInterestRate) {
                DincrPrimaryButton(tx("Guardar aportes", "Save contributions"), loading = saving, modifier = Modifier.testTag("salvavidas.auto.save"), onClick = onClick@{
                    var plan: SalvavidasPlanRequest? = null
                    if (showsFields) {
                        val value = AmountInput.parse(amount, format.separators)?.takeIf { it <= SalvavidasPlanRequest.MAX_AMOUNT }
                            ?: run { error = tx("Escribí un monto mayor que cero.", "Enter an amount above zero."); return@onClick }
                        val last = end
                        if (last != null && last.isBefore(start)) {
                            error = tx("La fecha final debe ser después del primer aporte.", "The end date must be after the first contribution."); return@onClick
                        }
                        plan = SalvavidasPlanRequest(enabled, value, frequency, start.toString(), last?.toString())
                    }
                    var balance: java.math.BigDecimal? = null
                    if (asksBalance) {
                        balance = AmountInput.parseZeroOrMore(savedToday, format.separators) ?: run {
                            error = tx("Indicá cuánto tenés ahorrado hoy (puede ser 0) para activar los aportes automáticos.",
                                "Enter how much you have saved today (it can be 0) to turn on automatic contributions."); return@onClick
                        }
                    }
                    var annual: java.math.BigDecimal? = null
                    if (s.offersInterestRate && rate.isNotBlank()) {
                        val parsed = SalvavidasRateInput.parse(rate) ?: run {
                            error = tx("Indicá una tasa de interés anual entre 0 % y 50 %.", "Enter an annual interest rate between 0% and 50%."); return@onClick
                        }
                        if (s.annualInterestRate == null || parsed.compareTo(s.annualInterestRate) != 0) annual = parsed
                    }
                    val update = SalvavidasUpdate.plan(plan, balance, annual) ?: run {
                        error = tx("No hay cambios para guardar.", "There are no changes to save."); return@onClick
                    }
                    error = null
                    save(update) { failure -> error = failure }
                })
            }
            if (editing) {
                TextButton({ editing = false }, enabled = !saving, modifier = Modifier.heightIn(min = 48.dp).testTag("salvavidas.auto.cancel")) {
                    Text(tx("Cancelar", "Cancel"), color = Dincr.colors.tint)
                }
            }
        }
    }
}
