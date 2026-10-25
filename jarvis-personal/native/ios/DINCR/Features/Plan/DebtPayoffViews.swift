import DincrCore
import DincrDesign
import SwiftUI

// When the debts are expected to be paid off (Owner and every plan): the backend's estimate per
// debt and the month all of them end. A debt it cannot estimate says so; no date is invented.
// Android: DebtPayoffViews.kt.

/// Above the debts list: how much of all the debts has been paid (a bar and the % left), the
/// debt-free month of the plan's strategy (Owner and VIP) and the month paying only the installments.
struct DebtPayoffSummary: View {
    let summary: DebtPayoff.Summary
    let total: DebtProgress.Amounts?
    let strategy: DebtProgress.StrategyDate?
    @Environment(\.moneyFormat) private var format

    var body: some View {
        if summary.active > 0 {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                if let total {
                    Text(tx("Pagado \(format.string(total.paid)) de \(format.string(total.original))",
                            "Paid \(format.string(total.paid)) of \(format.string(total.original))"))
                        .font(DincrFont.bodySmall.weight(.semibold)).foregroundStyle(DincrColor.text)
                    if let fraction = total.progress.fraction { DincrProgressBar(fraction: fraction) }
                    Text(tx("Te falta el \(Self.percent(total.remainingFraction)) de tus deudas.",
                            "\(Self.percent(total.remainingFraction)) of your debts left."))
                        .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                        .accessibilityIdentifier("debts.progress.total")
                } else {
                    Text(tx("No podemos sumar cuánto llevás pagado: falta el monto original de alguna deuda.",
                            "We can’t add up what you’ve paid: some debt is missing its original amount."))
                        .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                }
                if let strategy { strategyLine(strategy) }
                if let date = summary.debtFreeDate {
                    InfoRow(label: strategy == nil ? tx("Libre de deudas aprox.", "Debt-free around") : tx("Solo con las cuotas", "Installments only"),
                            value: DebtPayoff.monthLabel(date))
                    if strategy == nil {
                        Text(tx("Si seguís pagando la cuota de cada deuda.", "If you keep paying each debt’s instalment."))
                            .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                    }
                } else {
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

    @ViewBuilder private func strategyLine(_ strategy: DebtProgress.StrategyDate) -> some View {
        if let date = strategy.date {
            InfoRow(label: tx("Libre de deudas según tu estrategia", "Debt-free with your strategy"), value: DebtPayoff.monthLabel(date))
                .accessibilityIdentifier("debts.strategy.date")
            if let saved = strategy.monthsSaved, saved > 0 {
                Text(saved == 1 ? tx("1 mes antes que pagando solo las cuotas.", "1 month earlier than paying only the instalments.")
                                : tx("\(saved) meses antes que pagando solo las cuotas.", "\(saved) months earlier than paying only the instalments."))
                    .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            }
        } else {
            Text(strategy.needsRates
                 ? tx("Tu estrategia todavía no estima la fecha: falta la tasa de interés de alguna deuda.",
                      "Your strategy can’t estimate the date yet: some debt is missing its interest rate.")
                 : tx("Tu estrategia todavía no estima la fecha: lo que destinás a deudas no alcanza para cubrir los intereses.",
                      "Your strategy can’t estimate the date yet: what goes to debts doesn’t cover the interest."))
                .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                .accessibilityIdentifier("debts.strategy.unknown")
        }
    }

    private static func percent(_ fraction: Double) -> String { "\(Int((fraction * 100).rounded())) %" }
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
