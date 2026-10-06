import DincrCore
import DincrDesign
import SwiftUI

/// PARITY F1 — the DINCR tab. Free → monthly summary; Basic → reports; VIP (while
/// `vip_intelligence` is on) → Today, scenarios, monthly review and projections. The strategy lives
/// in the Plan tab (Estrategia, Distribución de dinero).
struct AdvisorHubView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ScreenScroll(title: "DINCR") {
            let tier = model.planTier
            let vip = tier == .vip && model.flags.isEnabled(.vipIntelligence)
            VStack(spacing: DincrSpacing.s2) {
                if vip {
                    link(TodayView(), "sun.max", tx("Hoy", "Today"), tx("Lo que DINCR vio en tus números", "What DINCR noticed in your numbers"), id: "advisor.today")
                    link(ScenariosView(), "slider.horizontal.3", tx("Escenarios", "Scenarios"), tx("¿Y si gano o gasto distinto?", "What if I earn or spend differently?"), id: "advisor.scenarios")
                    link(MonthlyReviewView(), "checklist", tx("Revisión del mes", "Monthly review"), tx("Cómo te fue y qué sigue", "How it went and what’s next"), id: "advisor.review")
                    link(ProjectionsView(), "chart.line.uptrend.xyaxis", tx("Proyecciones", "Projections"), tx("Tus próximos meses", "Your next months"), id: "advisor.projections")
                }
                link(MonthlySummaryView(), "calendar.badge.checkmark", tx("Resumen del mes", "Monthly summary"), tx("Ingresos, gastos y categorías", "Income, expenses and categories"), id: "advisor.summary")
                if tier.rank >= PlanTier.basic.rank && model.flags.isEnabled(.advancedReports) {
                    link(ReportsView(), "doc.text.magnifyingglass", tx("Reportes", "Reports"), tx("Comparación con el mes anterior", "Comparison with the previous month"), id: "advisor.reports")
                }
            }
            if tier == .free {
                PlanRequiredView(tier: .basic, feature: tx("La estrategia de DINCR", "DINCR’s strategy"))
            }
        }
    }

    private func link<Destination: View>(_ destination: Destination, _ symbol: String, _ title: String, _ subtitle: String, id: String) -> some View {
        NavigationLink { destination } label: { HubRow(symbol: symbol, title: title, subtitle: subtitle) }
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

/// PARITY F9 — DINCR Today (VIP proactive advisor).
struct TodayView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ScreenScroll(title: tx("Hoy", "Today")) {
            AsyncContent(load: { try await model.service.dincrToday() }) { today, _ in
                TodayContent(today: today)
            }
            FinancialDisclaimer()
        }
    }
}

private struct TodayContent: View {
    let today: DincrToday

    var body: some View {
        if today.isBaseline {
            // No earlier observation yet: changes can't be compared, but the current situation is known.
            StatusBanner(tone: .info, title: tx("Aprendiendo tu punto de partida", "Learning your starting point"),
                         message: today.advisor.message ?? tx("DINCR necesita una observación anterior para detectar cambios.", "DINCR needs an earlier observation to detect changes."))
                .accessibilityIdentifier("today.baseline")
            let current = today.currentAlerts ?? []
            if !current.isEmpty {
                Text(tx("Tu situación actual", "Your current situation")).font(DincrFont.title2).foregroundStyle(DincrColor.text)
                    .accessibilityAddTraits(.isHeader)
                ForEach(Array(current.enumerated()), id: \.offset) { _, alert in
                    DincrMessage(.financial(severity: alert.severity), title: alert.title ?? "",
                                 message: [alert.context, alert.action].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " "))
                        .accessibilityIdentifier("today.current.alert")
                }
            } else if today.currentAlerts != nil {
                EmptyStateView(symbol: "sun.max", title: tx("Nada urgente hoy", "Nothing urgent today"),
                               message: tx("Tu situación actual no tiene avisos.", "Your current situation has no alerts.")) { EmptyView() }
            }
        } else {
            let alerts = today.advisor.alerts ?? []
            if alerts.isEmpty {
                EmptyStateView(symbol: "sun.max", title: tx("Nada urgente", "Nothing urgent"),
                               message: today.advisor.message ?? tx("DINCR te avisa cuando algo cambie en tus números.", "DINCR lets you know when something changes in your numbers.")) { EmptyView() }
            }
            ForEach(Array(alerts.enumerated()), id: \.offset) { _, alert in
                DincrMessage(.financial(severity: alert.severity), title: alert.title ?? "", message: alert.explanation ?? "")
            }
        }
    }
}

/// PARITY F5 — projections and the debt plan (VIP), from the command center.
struct ProjectionsView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ScreenScroll(title: tx("Proyecciones", "Projections")) {
            AsyncContent(load: { try await model.service.commandCenter() }) { center, _ in
                ProjectionsContent(center: center)
            }
            FinancialDisclaimer()
        }
    }
}

private struct ProjectionsContent: View {
    let center: CommandCenter

    var body: some View {
        ForEach(Array((center.projections ?? []).enumerated()), id: \.offset) { _, point in
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                Text(tx("En \(point.months ?? 0) meses", "In \(point.months ?? 0) months")).font(DincrFont.title2)
                FigureRow(label: tx("Efectivo", "Cash"), amount: point.cash)
                FigureRow(label: tx("Deuda", "Debt"), amount: point.debt)
                FigureRow(label: tx("Patrimonio neto", "Net worth"), amount: point.netWorth)
            }
            .dincrCard()
        }
        if let plan = center.debtPlanner?.recommended {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                SectionHeader(title: tx("Plan de deudas recomendado", "Recommended debt plan"))
                InfoRow(label: tx("Empezar por", "Start with"), value: plan.target ?? "—")
                FigureRow(label: tx("Pago mensual al objetivo", "Monthly payment to the target"), amount: plan.monthlyToTarget)
                if let months = plan.months { InfoRow(label: tx("Tiempo estimado", "Estimated time"), value: tx("\(months) meses", "\(months) months")) }
                FigureRow(label: tx("Intereses estimados", "Estimated interest"), amount: plan.interest)
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
