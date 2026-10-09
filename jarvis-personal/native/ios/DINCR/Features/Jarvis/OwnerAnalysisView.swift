import Charts
import DincrCore
import DincrDesign
import SwiftUI

/// JARVIS · Análisis financiero (Owner only): the historical web Finanzas tab with the app's own
/// components. `GET /transactions/analysis/summary` (spending by category, income vs expenses,
/// expenses by month), `GET /finance/net-worth` and `GET /finance/engine` (health score, month-end
/// forecast, emergency fund, debt strategy, recommendations). Opened only for the Owner role:
/// `JarvisSectionView` (the full screen) and, since §15 PR 11, Movimientos → Análisis in the
/// `.analysis` mode. Every figure is the backend's.
struct OwnerAnalysisView: View {
    /// `.jarvis`: every section (JARVIS → Análisis financiero, unchanged). `.analysis`: the same data
    /// without the health score (canonical score: P3.7) and the net worth (Patrimonio headline: P0.9).
    enum Mode { case jarvis, analysis }

    @Environment(AppModel.self) private var model
    var mode: Mode = .jarvis

    var body: some View {
        ScreenScroll(title: tx("Análisis financiero", "Financial analysis")) {
            AsyncContent(fallback: tx("No pudimos cargar tu análisis.", "We couldn’t load your analysis."),
                         load: { try await model.service.ownerAnalysis() }) { analysis, _ in
                OwnerAnalysisContent(analysis: analysis, mode: mode)
            }
            FinancialDisclaimer()
        }
    }
}

private struct OwnerAnalysisContent: View {
    let analysis: OwnerAnalysis
    let mode: OwnerAnalysisView.Mode

    var body: some View {
        let engine = analysis.engine
        let worth = analysis.netWorth
        let transactions = analysis.transactions

        if mode == .jarvis, let health = engine.health, let score = health.score {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                SectionHeader(title: tx("Salud financiera", "Financial health"))
                InfoRow(label: OwnerAnalysisText.healthLevel(health.level), value: "\(Int(score.rounded()))/100")
                DincrProgressBar(fraction: score / 100)
            }
            .dincrCard()
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("jarvis.analysis.health")
        }

        if mode == .jarvis {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                SectionHeader(title: tx("Patrimonio", "Net worth"))
                MoneyText(worth.netWorth, font: DincrFont.displayAmount)
                FigureRow(label: tx("Activos", "Assets"), amount: worth.assets?.assetsTotal)
                FigureRow(label: tx("Deudas", "Debts"), amount: worth.liabilities?.debtTotal)
                FigureRow(label: tx("Cuotas mensuales", "Monthly payments"), amount: worth.liabilities?.monthlyDebtPayments)
                if let change = worth.change?.amount {
                    FigureRow(label: tx("Cambio desde la última lectura", "Change since the last reading"), amount: change)
                }
                if let interpretation = worth.interpretation {
                    Text(interpretation).font(DincrFont.caption).foregroundStyle(DincrColor.text2)
                }
            }
            .dincrCard()
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("jarvis.analysis.networth")
        }

        let flow = transactions.flowMonths()
        if !flow.isEmpty {
            VStack(alignment: .leading, spacing: DincrSpacing.s3) {
                SectionHeader(title: tx("Ingresos y gastos", "Income and expenses"))
                IncomeExpenseChart(months: flow)
            }
            .dincrCard()
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("jarvis.analysis.flow")
        }

        let byMonth = (transactions.expensesByMonth ?? []).filter { !$0.month.isEmpty && $0.total != nil }.suffix(6)
        if !byMonth.isEmpty {
            VStack(alignment: .leading, spacing: DincrSpacing.s3) {
                SectionHeader(title: tx("Gastos por mes", "Expenses by month"))
                MonthBars(points: Array(byMonth))
            }
            .dincrCard()
        }

        let categories = transactions.spendingCategories
        if !categories.isEmpty {
            VStack(alignment: .leading, spacing: DincrSpacing.s3) {
                SectionHeader(title: tx("Distribución del gasto", "Spending by category"))
                if let label = transactions.spendingBreakdown?.period?.label {
                    Text(label).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                }
                SpendingDonut(rows: transactions.spendingBreakdown?.categories ?? [])
                CategoryBars(categories: categories, limit: SpendingDonut.barsLimit)
            }
            .dincrCard()
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("jarvis.analysis.spending")
        }

        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            SectionHeader(title: tx("Cierre del mes", "Month end"))
                .accessibilityIdentifier("jarvis.analysis.monthEnd")
            FigureRow(label: tx("Saldo proyectado al cierre", "Projected month-end balance"), amount: engine.forecast?.projectedEndBalance)
            if let alert = engine.forecast?.alert?.message {
                Text(alert).font(DincrFont.caption).foregroundStyle(DincrColor.warning)
            }
            if let fund = engine.emergencyFund {
                FigureRow(label: tx("Salvavidas actual", "Current emergency fund"), amount: fund.current)
                FigureRow(label: tx("Meta de 6 meses", "6-month target"), amount: fund.recommended6Months)
                if let months = fund.coverageMonths {
                    InfoRow(label: tx("Cobertura", "Coverage"), value: tx(String(format: "%.1f meses", months), String(format: "%.1f months", months)))
                }
            }
            if let target = engine.debts?.recommended?.priorityDebt {
                InfoRow(label: tx("Deuda prioritaria", "Priority debt"), value: target.name ?? "—")
                FigureRow(label: tx("Saldo", "Balance"), amount: target.remainingAmount)
            }
        }
        .dincrCard()

        let recommendations = (engine.recommendations ?? []) + (worth.recommendations ?? [])
        if !recommendations.isEmpty {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                SectionHeader(title: tx("Recomendaciones", "Recommendations"))
                ForEach(Array(recommendations.enumerated()), id: \.offset) { _, text in
                    Label { Text(text).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2) } icon: {
                        Image(systemName: "lightbulb").foregroundStyle(DincrColor.tint)
                    }
                }
            }
            .dincrCard()
        }
    }
}

/// Expenses per month as bars, in calendar order, with a table alternative for VoiceOver.
private struct MonthBars: View {
    let points: [TransactionAnalysis.MonthPoint]
    @Environment(\.moneyFormat) private var format

    var body: some View {
        Chart {
            ForEach(points) { point in
                BarMark(x: .value("Mes", point.month), y: .value("Monto", NSDecimalNumber(decimal: point.total ?? 0).doubleValue))
                    .foregroundStyle(DincrColor.chartExpense)
                    .clipShape(UnevenRoundedRectangle(topLeadingRadius: 4, topTrailingRadius: 4))
            }
        }
        .chartYAxis {
            AxisMarks(position: .leading, values: .automatic(desiredCount: 3)) { _ in
                AxisGridLine().foregroundStyle(DincrColor.line)
                AxisValueLabel().font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            }
        }
        .chartXAxis {
            AxisMarks { _ in AxisValueLabel().font(DincrFont.caption).foregroundStyle(DincrColor.textMuted) }
        }
        .frame(height: 160)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(tx("Gastos por mes", "Expenses by month"))
        .accessibilityValue(points.map { "\($0.month): \(format.spoken($0.total ?? 0))" }.joined(separator: "; "))
    }
}

/// Spending by category as a donut (the backend's categories as they are; nothing is regrouped),
/// with the bars below as the readable list. Pilot consumer of the shared `CompositionDonut`
/// (DESIGN.md → Data visualization): same rows, one hue instead of the default rainbow, a
/// selectable part, and the parts read by VoiceOver. A row without a total stays unknown (so no
/// proportions are claimed), the sum of the parts is not shown as a total (the backend has its
/// own), and when the bars below list only some categories the donut keeps its own legend so every
/// category stays named, as the previous chart's legend did.
private struct SpendingDonut: View {
    let rows: [TransactionAnalysis.CategoryTotal]
    static let barsLimit = 8

    var body: some View {
        CompositionDonut(
            title: tx("Distribución del gasto", "Spending by category"),
            composition: Composition(rows.enumerated().map { index, row in
                CompositionItem(id: "\(index)-\(row.category ?? "")", label: CategoryStyle.label(row.category), value: row.total)
            }),
            color: DincrColor.chartExpense,
            showsLegend: rows.count > Self.barsLimit,
            showsTotal: false
        )
    }
}

enum OwnerAnalysisText {
    static func healthLevel(_ level: String?) -> String {
        switch level {
        case "strong"?: tx("Fuerte", "Strong")
        case "stable"?: tx("Estable", "Stable")
        case "fragile"?: tx("Frágil", "Fragile")
        case "critical"?: tx("Crítica", "Critical")
        default: tx("Puntaje", "Score")
        }
    }
}
