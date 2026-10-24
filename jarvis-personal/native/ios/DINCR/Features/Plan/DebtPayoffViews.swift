import DincrCore
import DincrDesign
import SwiftUI

// When the debts are expected to be paid off (Owner and every plan): the backend's estimate per
// debt and the month all of them end. A debt it cannot estimate says so; no date is invented.
// Android: DebtPayoffViews.kt.

/// "Libre de deudas aprox.: oct 2027", above the debts list.
struct DebtPayoffSummary: View {
    let summary: DebtPayoff.Summary

    var body: some View {
        if summary.active > 0 {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                if let date = summary.debtFreeDate {
                    InfoRow(label: tx("Libre de deudas aprox.", "Debt-free around"), value: DebtPayoff.monthLabel(date))
                    Text(tx("Si seguís pagando la cuota de cada deuda.", "If you keep paying each debt’s instalment."))
                        .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                } else {
                    Text(tx("Todavía no podemos estimar cuándo terminás de pagar todas tus deudas.",
                            "We can’t estimate yet when you’ll finish paying all your debts."))
                        .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                    Text(summary.unestimated == 1
                         ? tx("1 deuda sin fecha: falta la tasa de interés o la cuota no alcanza para los intereses.",
                              "1 debt without a date: the interest rate is missing or the instalment doesn’t cover the interest.")
                         : tx("\(summary.unestimated) deudas sin fecha: falta la tasa de interés o la cuota no alcanza para los intereses.",
                              "\(summary.unestimated) debts without a date: the interest rate is missing or the instalment doesn’t cover the interest."))
                        .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                }
            }
            .dincrCard()
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("debts.payoff.summary")
        }
    }
}

/// "Terminás de pagar: oct 2027 · 12 cuotas" under each unpaid debt.
struct DebtPayoffLine: View {
    let debt: Debt

    var body: some View {
        if (debt.remainingAmount ?? 0) > 0 {
            Group {
                if let date = debt.estimatedPayoffDate, let months = debt.estimatedPayoffMonths, months > 0 {
                    InfoRow(label: tx("Terminás de pagar", "Paid off by"),
                            value: "\(DebtPayoff.monthLabel(date)) · " + (months == 1 ? tx("1 cuota", "1 instalment") : tx("\(months) cuotas", "\(months) instalments")))
                } else {
                    Text(tx("Sin fecha estimada: falta la tasa de interés o la cuota no alcanza para los intereses.",
                            "No estimated date: the interest rate is missing or the instalment doesn’t cover the interest."))
                        .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                }
            }
            .accessibilityIdentifier("debt.payoff.\(debt.id)")
        }
    }
}
