package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import com.dincr.app.tx
import com.dincr.data.Debt
import com.dincr.data.DebtPayoff
import com.dincr.data.DebtProgress
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal

// When the debts are expected to be paid off (Owner and every plan): the backend's estimate per
// debt and the month all of them end. A debt it cannot estimate says so; no date is invented.
// iOS: DebtPayoffViews.swift.

/**
 * Above the debts list: how much of all the debts has been paid (a bar and the % left), the
 * debt-free month of the plan's strategy (Owner and VIP) and the month paying only the installments.
 */
@Composable
fun DebtPayoffSummary(summary: DebtPayoff.Summary, total: DebtProgress.Amounts?, strategy: DebtProgress.StrategyDate?) {
    if (summary.active == 0) return
    DincrCard(Modifier.testTag("debts.payoff.summary")) {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
            if (total != null) {
                ProgressLine(total.ratio, tx("Pagado ${Dincr.money.format(total.paid)} de ${Dincr.money.format(total.original)}",
                    "Paid ${Dincr.money.format(total.paid)} of ${Dincr.money.format(total.original)}"))
                Caption(tx("Te falta el ${percent(total.remainingFraction)} de tus deudas.", "${percent(total.remainingFraction)} of your debts left."))
            } else {
                Caption(tx("No podemos sumar cuánto llevás pagado: falta el monto original de alguna deuda.",
                    "We can’t add up what you’ve paid: some debt is missing its original amount."))
            }
            strategy?.let { StrategyLine(it) }
            val date = summary.debtFreeDate
            if (date != null) {
                InfoLine(if (strategy == null) tx("Libre de deudas aprox.", "Debt-free around") else tx("Solo con las cuotas", "Installments only"),
                    DebtPayoff.monthLabel(date))
                if (strategy == null) Caption(tx("Si seguís pagando la cuota de cada deuda.", "If you keep paying each debt’s instalment."))
            } else {
                Caption(if (summary.unestimated == 1)
                    tx("1 deuda sin fecha: falta la tasa de interés o la cuota no alcanza para los intereses.",
                        "1 debt without a date: the interest rate is missing or the instalment doesn’t cover the interest.")
                else tx("${summary.unestimated} deudas sin fecha: falta la tasa de interés o la cuota no alcanza para los intereses.",
                    "${summary.unestimated} debts without a date: the interest rate is missing or the instalment doesn’t cover the interest."))
            }
        }
    }
}

@Composable
private fun StrategyLine(strategy: DebtProgress.StrategyDate) {
    val date = strategy.date
    if (date != null) {
        Column(Modifier.testTag("debts.strategy.date")) {
            InfoLine(tx("Libre de deudas según tu estrategia", "Debt-free with your strategy"), DebtPayoff.monthLabel(date))
        }
        strategy.monthsSaved?.takeIf { it > 0 }?.let { saved ->
            Caption(if (saved == 1) tx("1 mes antes que pagando solo las cuotas.", "1 month earlier than paying only the instalments.")
            else tx("$saved meses antes que pagando solo las cuotas.", "$saved months earlier than paying only the instalments."))
        }
    } else {
        Column(Modifier.testTag("debts.strategy.unknown")) {
            Caption(if (strategy.needsRates) tx("Tu estrategia todavía no estima la fecha: falta la tasa de interés de alguna deuda.",
                "Your strategy can’t estimate the date yet: some debt is missing its interest rate.")
            else tx("Tu estrategia todavía no estima la fecha: lo que destinás a deudas no alcanza para cubrir los intereses.",
                "Your strategy can’t estimate the date yet: what goes to debts doesn’t cover the interest."))
        }
    }
}

private fun percent(fraction: Double) = "${Math.round(fraction * 100)} %"

/** "Terminás de pagar: oct 2027 · 12 cuotas" under each unpaid debt. */
@Composable
fun DebtPayoffLine(debt: Debt) {
    if ((debt.remainingAmount ?: BigDecimal.ZERO).signum() <= 0) return
    Column(Modifier.testTag("debt.payoff.${debt.id}")) {
        val date = debt.estimatedPayoffDate
        val months = debt.estimatedPayoffMonths
        if (date != null && months != null && months > 0) {
            InfoLine(tx("Terminás de pagar", "Paid off by"),
                DebtPayoff.monthLabel(date) + " · " + if (months == 1) tx("1 cuota", "1 instalment") else tx("$months cuotas", "$months instalments"))
        } else {
            Caption(tx("Sin fecha estimada: falta la tasa de interés o la cuota no alcanza para los intereses.",
                "No estimated date: the interest rate is missing or the instalment doesn’t cover the interest."))
        }
    }
}
