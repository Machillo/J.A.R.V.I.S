import DincrCore
import DincrDesign
import SwiftUI

/// UX-13 — Movimientos → Análisis: the monthly summary (every plan), reports (Basic+, paused with
/// `advanced_reports`) and the monthly review (VIP, paused with `vip_intelligence`). The same screens
/// the retired DINCR tab opened; below its plan a row stays visible, locked, and opens Suscripción.
struct AnalysisHubView: View {
    var body: some View {
        ScreenScroll(title: tx("Análisis", "Analysis")) {
            VStack(spacing: DincrSpacing.s2) {
                GatedEntry(minimum: .free, flag: nil, symbol: "calendar.badge.checkmark", title: tx("Resumen del mes", "Monthly summary"),
                           subtitle: tx("Ingresos, gastos y categorías", "Income, expenses and categories"), id: "analysis.summary") { MonthlySummaryView() }
                GatedEntry(minimum: .basic, flag: .advancedReports, symbol: "doc.text.magnifyingglass", title: tx("Reportes", "Reports"),
                           subtitle: tx("Comparación con el mes anterior", "Comparison with the previous month"), id: "analysis.reports") { ReportsView() }
                GatedEntry(minimum: .vip, flag: .vipIntelligence, symbol: "checklist", title: tx("Revisión del mes", "Monthly review"),
                           subtitle: tx("Cómo te fue y qué sigue", "How it went and what’s next"), id: "analysis.review") { MonthlyReviewView() }
            }
        }
    }
}

/// UX-13 — the Patrimonio tab: projections and scenarios (VIP, paused with `vip_intelligence`), the
/// same screens the retired DINCR tab opened. Only what UX-13 needs: no new figure or calculation.
struct WealthHubView: View {
    var body: some View {
        ScreenScroll(title: tx("Patrimonio", "Wealth")) {
            VStack(spacing: DincrSpacing.s2) {
                GatedEntry(minimum: .vip, flag: .vipIntelligence, symbol: "chart.line.uptrend.xyaxis", title: tx("Proyecciones", "Projections"),
                           subtitle: tx("Tus próximos meses", "Your next months"), id: "wealth.projections") { ProjectionsView() }
                GatedEntry(minimum: .vip, flag: .vipIntelligence, symbol: "slider.horizontal.3", title: tx("Escenarios", "Scenarios"),
                           subtitle: tx("¿Y si gano o gasto distinto?", "What if I earn or spend differently?"), id: "wealth.scenarios") { ScenariosView() }
            }
        }
    }
}

/// One entry of a hub: open while the plan includes it, locked below its plan (opens Suscripción),
/// paused while its operational switch is off. Same policy as the Plan tab's rows.
private struct GatedEntry<Destination: View>: View {
    @Environment(AppModel.self) private var model
    let minimum: PlanTier
    let flag: OpsFlag?
    let symbol: String
    let title: String
    let subtitle: String
    let id: String
    @ViewBuilder let destination: () -> Destination

    var body: some View {
        Group {
            if model.planTier.rank < minimum.rank {
                NavigationLink { PlanSettingsView() } label: {
                    HubRow(symbol: symbol, title: title, subtitle: tx("Disponible desde \(PlanLabel.name(minimum.rawValue))", "Available from \(PlanLabel.name(minimum.rawValue))"), locked: minimum)
                }
                .accessibilityHint(tx("Abre Suscripción", "Opens Subscription"))
            } else if let flag, !model.flags.isEnabled(flag) {
                NavigationLink {
                    ScreenScroll(title: title) { FeaturePausedView(message: model.flags.message(flag, language: model.language)) }
                } label: { HubRow(symbol: symbol, title: title, subtitle: tx("En pausa por mantenimiento", "Paused for maintenance")) }
            } else {
                NavigationLink { destination() } label: { HubRow(symbol: symbol, title: title, subtitle: subtitle) }
            }
        }
        .buttonStyle(.plain)
        .dincrCard(padding: DincrSpacing.s3)
        .accessibilityIdentifier(id)
    }
}

/// PARITY D7 — monthly summary (Free and up).
struct MonthlySummaryView: View {
    @Environment(AppModel.self) private var model
    @State private var period = Period.current

    var body: some View {
        ScreenScroll(title: tx("Resumen del mes", "Monthly summary")) {
            MonthPicker(period: $period)
            AsyncContent(load: { try await model.service.monthlySummary(period: period) }) { summary, _ in
                SummaryContent(summary: summary)
            }
            .id(period)
        }
    }
}

private struct SummaryContent: View {
    let summary: MonthlySummary

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            FigureRow(label: tx("Ingresos", "Income"), amount: summary.income, sign: .income)
            FigureRow(label: tx("Gastos", "Expenses"), amount: summary.expenses, sign: .expense)
            FigureRow(label: tx("Pagado a deudas", "Paid to debts"), amount: summary.debtPaid)
            FigureRow(label: tx("Balance", "Balance"), amount: summary.balance)
            FigureRow(label: tx("Ahorrado", "Saved"), amount: summary.savings)
        }
        .dincrCard()
        let categories = (summary.categories ?? []).compactMap { item in item.category.map { CategoryAmount(category: $0, amount: item.amount ?? 0) } }
        if !categories.isEmpty {
            VStack(alignment: .leading, spacing: DincrSpacing.s3) {
                SectionHeader(title: tx("En qué se fue el dinero", "Where the money went"))
                CategoryBars(categories: categories)
            }
            .dincrCard()
        }
    }
}

/// The Basic strategy's figures (`/finance/strategy-basic`), shown by the Plan tab's Estrategia.
/// `showsAllocations`: the split lives in Distribución de dinero.
struct StrategyContent: View {
    let strategy: Strategy
    var showsAllocations = true
    /// "Tu plan del mes" already leads with the recommendation and keeps the cautions in sight.
    var showsRecommendation = true
    var showsWarnings = true

    var body: some View {
        if showsRecommendation, let recommendation = strategy.recommendation ?? strategy.directorNote {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                SectionHeader(title: tx("Recomendación", "Recommendation"))
                Text(recommendation).font(DincrFont.body).foregroundStyle(DincrColor.text)
            }
            .dincrCard()
        }
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            SectionHeader(title: tx("Tu mes", "Your month"))
            FigureRow(label: tx("Ingreso mensual", "Monthly income"), amount: strategy.monthlyIncome)
            FigureRow(label: tx("Gastos esenciales", "Essential expenses"), amount: strategy.essentialExpenses)
            FigureRow(label: tx("Cuotas mínimas", "Minimum payments"), amount: strategy.minimumDebtPayments)
            FigureRow(label: tx("Margen para decidir", "Margin to decide"), amount: strategy.strategicMargin)
        }
        .dincrCard()
        let allocations = (strategy.vipAllocations?.isEmpty == false ? strategy.vipAllocations : strategy.allocations) ?? []
        if showsAllocations && !allocations.isEmpty {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                SectionHeader(title: tx("Cómo repartirlo", "How to split it"))
                ForEach(Array(allocations.enumerated()), id: \.offset) { _, allocation in
                    FigureRow(label: allocation.label ?? allocation.bucket ?? "", amount: allocation.amount)
                }
            }
            .dincrCard()
        }
        if let projection = strategy.projection, let months = projection.months {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                SectionHeader(title: tx("Tu deuda prioritaria", "Your priority debt"))
                InfoRow(label: projection.name ?? "", value: tx("\(months) meses", "\(months) months"))
                if let baseline = projection.baselineMonths, baseline > months {
                    Text(tx("\(baseline - months) meses antes que pagando solo el mínimo.", "\(baseline - months) months sooner than paying only the minimum."))
                        .font(DincrFont.caption).foregroundStyle(DincrColor.positive)
                }
            }
            .dincrCard()
        }
        ForEach(Array((showsWarnings ? strategy.warnings ?? [] : []).enumerated()), id: \.offset) { _, warning in
            DincrMessage(.attention, title: tx("Tomá en cuenta", "Keep in mind"), message: warning)
        }
    }
}

/// PARITY F6 — what-if scenarios (VIP). The simulation is read-only: nothing is saved.
struct ScenariosView: View {
    @Environment(AppModel.self) private var model
    @State private var income = ""
    @State private var expenses = ""
    @State private var extra = ""
    @State private var result: ScenarioResult?
    @State private var error: String?
    @State private var running = false

    var body: some View {
        ScreenScroll(title: tx("Escenarios", "Scenarios")) {
            VStack(alignment: .leading, spacing: DincrSpacing.s3) {
                Text(tx("Probá cambios sin guardar nada. Usá − para una baja.", "Try changes without saving anything. Use − for a decrease."))
                    .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                MoneyField(label: tx("Cambio en ingreso mensual", "Change in monthly income"), text: $income)
                MoneyField(label: tx("Cambio en gastos mensuales", "Change in monthly expenses"), text: $expenses)
                MoneyField(label: tx("Dinero extra una vez", "One-time extra money"), text: $extra)
                if let error { Text(error).font(DincrFont.caption).foregroundStyle(DincrColor.negative) }
                Button(tx("Simular", "Simulate")) { Task { await simulate() } }
                    .buttonStyle(.dincrPrimary(loading: running))
                    .disabled(running)
                    .accessibilityIdentifier("scenario.run")
            }
            .dincrCard()
            if let result {
                VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                    SectionHeader(title: tx("Resultado", "Result"))
                    FigureRow(label: tx("Margen actual", "Current margin"), amount: result.current?.strategicMargin)
                    FigureRow(label: tx("Margen en el escenario", "Margin in the scenario"), amount: result.scenario?.strategicMargin)
                    FigureRow(label: tx("Diferencia", "Difference"), amount: result.delta?.strategicMargin)
                }
                .dincrCard()
            }
            FinancialDisclaimer()
        }
    }

    /// A signed amount: "−5.000" / "-5.000" decreases. Empty is zero.
    private func signed(_ text: String) -> Decimal? {
        let trimmed = text.trimmingCharacters(in: .whitespaces)
        if trimmed.isEmpty { return 0 }
        let negative = trimmed.hasPrefix("-") || trimmed.hasPrefix("−")
        let digits = negative ? String(trimmed.dropFirst()) : trimmed
        guard let value = AmountInput.parse(digits, separators: model.moneyFormat.separators) else { return nil }
        return negative ? -value : value
    }

    private func simulate() async {
        guard let incomeChange = signed(income), let expenseChange = signed(expenses), let oneTime = signed(extra), oneTime >= 0 else {
            error = model.moneyFormat.amountHint; return
        }
        running = true; error = nil
        defer { running = false }
        let epoch = model.currentEpoch
        do {
            result = try await model.service.simulate(ScenarioRequest(monthlyIncomeChange: incomeChange, monthlyExpenseChange: expenseChange, oneTimeExtra: oneTime))
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos simularlo.", "We couldn’t simulate it."))
        }
    }
}

/// PARITY F8 — monthly review (VIP).
struct MonthlyReviewView: View {
    @Environment(AppModel.self) private var model
    @State private var period = Period.current

    var body: some View {
        ScreenScroll(title: tx("Revisión del mes", "Monthly review")) {
            MonthPicker(period: $period)
            AsyncContent(load: { try await model.service.monthlyReview(period: period) }) { review, _ in
                ReviewContent(review: review)
            }
            .id(period)
            FinancialDisclaimer()
        }
    }
}

private struct ReviewContent: View {
    let review: MonthlyReview

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Text(review.headline ?? tx("Tu mes", "Your month")).font(DincrFont.title2)
            if let summary = review.summary { Text(summary).font(DincrFont.body).foregroundStyle(DincrColor.text2) }
        }
        .dincrCard()
        ForEach(Array((review.scorecard ?? []).enumerated()), id: \.offset) { _, line in
            InfoRow(label: line.label ?? line.key ?? "",
                    value: line.explanation ?? [line.current.map { String(format: "%.0f", $0) }, line.unit].compactMap { $0 }.joined(separator: " "))
                .dincrCard(padding: DincrSpacing.s3)
        }
        if let next = review.nextMonth {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                SectionHeader(title: tx("El próximo mes", "Next month"))
                Text(next.title ?? "").font(DincrFont.body.weight(.semibold))
                if let amount = next.amount { FigureRow(label: tx("Monto sugerido", "Suggested amount"), amount: amount) }
                if let rationale = next.rationale { Text(rationale).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted) }
            }
            .dincrCard()
        }
    }
}

/// Reports (Basic; `advanced_reports`).
struct ReportsView: View {
    @Environment(AppModel.self) private var model
    @State private var period = Period.current

    var body: some View {
        ScreenScroll(title: tx("Reportes", "Reports")) {
            MonthPicker(period: $period)
            AsyncContent(load: { try await model.service.report(period: period) }) { report, _ in
                ReportContent(report: report)
            }
            .id(period)
        }
    }
}

private struct ReportContent: View {
    let report: MonthReport

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            FigureRow(label: tx("Ingresos", "Income"), amount: report.income, sign: .income)
            FigureRow(label: tx("Gastos", "Expenses"), amount: report.expenses, sign: .expense)
            FigureRow(label: tx("Pagado a deudas", "Paid to debts"), amount: report.debtPaid)
            FigureRow(label: tx("Aportes a metas", "Goal contributions"), amount: report.goalContributions)
            FigureRow(label: tx("Ahorrado", "Saved"), amount: report.saved)
        }
        .dincrCard()
        if let comparison = report.comparison {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                SectionHeader(title: tx("Mes anterior", "Previous month"))
                FigureRow(label: tx("Ingresos", "Income"), amount: comparison.income)
                FigureRow(label: tx("Gastos", "Expenses"), amount: comparison.expenses)
            }
            .dincrCard()
        }
    }
}
