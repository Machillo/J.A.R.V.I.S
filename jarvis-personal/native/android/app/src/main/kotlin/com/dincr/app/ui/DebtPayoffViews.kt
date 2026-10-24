package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import com.dincr.app.tx
import com.dincr.data.Debt
import com.dincr.data.DebtPayoff
import com.dincr.design.DincrCard
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal

// When the debts are expected to be paid off (Owner and every plan): the backend's estimate per
// debt and the month all of them end. A debt it cannot estimate says so; no date is invented.
// iOS: DebtPayoffViews.swift.

/** "Libre de deudas aprox.: oct 2027", above the debts list. */
@Composable
fun DebtPayoffSummary(summary: DebtPayoff.Summary) {
    if (summary.active == 0) return
    DincrCard(Modifier.testTag("debts.payoff.summary")) {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
            val date = summary.debtFreeDate
            if (date != null) {
                InfoLine(tx("Libre de deudas aprox.", "Debt-free around"), DebtPayoff.monthLabel(date))
                Caption(tx("Si seguís pagando la cuota de cada deuda.", "If you keep paying each debt’s instalment."))
            } else {
                Caption(tx("Todavía no podemos estimar cuándo terminás de pagar todas tus deudas.",
                    "We can’t estimate yet when you’ll finish paying all your debts."))
                Caption(if (summary.unestimated == 1)
                    tx("1 deuda sin fecha: falta la tasa de interés o la cuota no alcanza para los intereses.",
                        "1 debt without a date: the interest rate is missing or the instalment doesn’t cover the interest.")
                else tx("${summary.unestimated} deudas sin fecha: falta la tasa de interés o la cuota no alcanza para los intereses.",
                    "${summary.unestimated} debts without a date: the interest rate is missing or the instalment doesn’t cover the interest."))
            }
        }
    }
}

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
