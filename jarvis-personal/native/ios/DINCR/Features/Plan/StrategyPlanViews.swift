import DincrCore
import DincrDesign
import SwiftUI

/// PARITY F2/F3 — Estrategia (Plan tab). Three contracts, chosen from the server role and plan
/// (`StrategySource`): Basic reads `/finance/strategy-basic`, VIP Users `/vip/strategy-dashboard`,
/// the Owner `/jarvis/premium/strategy-dashboard`. Every figure is the backend's.
struct PlanStrategyView: View {
    var body: some View {
        ScreenScroll(title: tx("Estrategia", "Strategy")) {
            StrategyLoader { strategy in
                StrategyPlanContent(strategy: strategy)
            }
            FinancialDisclaimer()
        }
    }
}

/// Distribución de dinero (Plan tab): the same strategy answer as Estrategia, showing how the month's
/// surplus is split. Basic: strategy-basic `allocations`; VIP Users and the Owner: the dashboard's
/// `allocation_items`, base amount and formula.
struct DistributionView: View {
    var body: some View {
        ScreenScroll(title: tx("Distribución de dinero", "Money distribution")) {
            StrategyLoader { strategy in
                DistributionContent(strategy: strategy)
            }
            FinancialDisclaimer()
        }
    }
}

/// Loads the identity's strategy once per screen; Free sees what the plan includes instead.
struct StrategyLoader<Content: View>: View {
    @Environment(AppModel.self) private var model
    @ViewBuilder let content: (PlanStrategy) -> Content

    var body: some View {
        let source = StrategySource.of(model.profile, flags: model.flags)
        if source == .unavailable {
            PlanRequiredView(tier: .basic, feature: tx("La estrategia de DINCR", "DINCR’s strategy"))
        } else {
            AsyncContent(load: { try await model.service.planStrategy(source) }) { strategy, _ in
                content(strategy)
            }
            .id(source)
        }
    }
}

/// No income to plan with: ask for the financial situation (never a strategy built on zero).
struct NeedsIncomeState: View {
    let message: String?

    var body: some View {
        EmptyStateView(symbol: "banknote", title: tx("Necesitamos tus ingresos", "We need your income"),
                       message: message ?? tx("Registrá tus ingresos o completá tu situación financiera para armar tu estrategia.",
                                              "Record your income or complete your financial situation to build your strategy.")) {
            NavigationLink { SituationView() } label: { Text(tx("Completar situación financiera", "Complete financial situation")) }
                .buttonStyle(.dincrPrimary)
                .accessibilityIdentifier("strategy.completeSituation")
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("strategy.needsIncome")
    }
}

/// The income is an estimate from recorded movements, not declared.
struct ObservedIncomeNote: View {
    var body: some View {
        StatusBanner(tone: .info, title: IncomeSourceLabel.observedNote(),
                     message: tx("Declará tu ingreso en Perfil → Situación financiera para una estrategia más precisa.",
                                 "Declare your income in Profile → Financial situation for a more precise strategy."))
    }
}

private struct StrategyPlanContent: View {
    let strategy: PlanStrategy

    var body: some View {
        switch strategy {
        case .basic(let basic):
            if basic.needsIncome {
                NeedsIncomeState(message: basic.recommendation)
            } else {
                if basic.usesObservedIncome { ObservedIncomeNote() }
                StrategyContent(strategy: basic, showsAllocations: false)
            }
        case .dashboard(let dashboard):
            if let plan = dashboard.strategy {
                if plan.needsIncome {
                    NeedsIncomeState(message: plan.objective ?? dashboard.content)
                } else {
                    DashboardStrategyContent(title: dashboard.title, plan: plan)
                }
            } else {
                EmptyStateView(symbol: "map", title: tx("Sin estrategia por ahora", "No strategy for now"),
                               message: dashboard.content ?? tx("Volvé a intentarlo más tarde.", "Try again later.")) { EmptyView() }
            }
        }
    }
}

/// VIP Users and Owner dashboard. Owner-only figures appear only when the backend sent the Owner
/// model (`scope == "owner"`); a Users answer never shows a cash balance.
private struct DashboardStrategyContent: View {
    let title: String?
    let plan: DashboardStrategy

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Text(title ?? plan.title ?? tx("Tu estrategia", "Your strategy")).font(DincrFont.title2).foregroundStyle(DincrColor.text)
                .accessibilityAddTraits(.isHeader)
            if let objective = plan.objective { Text(objective).font(DincrFont.body).foregroundStyle(DincrColor.text2) }
        }
        .dincrCard()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("strategy.dashboard")

        if let priority = plan.priority, priority.title != nil || priority.detail != nil {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                SectionHeader(title: tx("Tu prioridad", "Your priority"))
                if let headline = priority.title { Text(headline).font(DincrFont.body.weight(.semibold)).foregroundStyle(DincrColor.text) }
                if let detail = priority.detail { Text(detail).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2) }
            }
            .dincrCard()
        }

        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            SectionHeader(title: tx("Tu mes", "Your month"))
            FigureRow(label: tx("Ingreso mensual", "Monthly income"), amount: plan.monthlyIncome)
            if let source = IncomeSourceLabel.label(plan.incomePolicy?.source) {
                Text(source).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            }
            FigureRow(label: tx("Gastos registrados este mes", "Spending recorded this month"), amount: plan.monthlyExpenses)
            FigureRow(label: tx("Cuotas de deuda pendientes", "Pending debt payments"), amount: plan.debtCommitmentCurrentCycle)
            // Recurring obligations not yet covered by the spending recorded this month (backend figure).
            FigureRow(label: tx("Obligaciones recurrentes sin cubrir", "Recurring obligations not yet covered"), amount: plan.pendingRecurringTotal)
            FigureRow(label: tx("Podés gastar con tranquilidad", "Safe to spend"), amount: plan.safeToSpend)
        }
        .dincrCard()

        if let fund = plan.emergencyFund {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                SectionHeader(title: "Salvavidas")
                FigureRow(label: tx("Ahorro actual", "Current savings"), amount: fund.current)
                FigureRow(label: tx("Base mensual", "Monthly base"), amount: fund.monthlyBase)
                FigureRow(label: tx("Próxima meta", "Next target"), amount: fund.nextTarget)
                FigureRow(label: tx("Te falta", "Still missing"), amount: fund.gapToNextTarget)
                if let level = StrategyText.emergencyLevel(fund.level) { InfoRow(label: tx("Nivel", "Level"), value: level) }
            }
            .dincrCard()
        }

        let timeline = plan.timeline ?? []
        if !timeline.isEmpty || plan.totalDebt != nil {
            VStack(alignment: .leading, spacing: DincrSpacing.s3) {
                SectionHeader(title: tx("Plan de deudas", "Debt plan"))
                ForEach(Array(timeline.enumerated()), id: \.offset) { index, item in
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(item.priority ?? index + 1). \(item.name ?? tx("Deuda", "Debt"))").font(DincrFont.body.weight(.semibold))
                        FigureRow(label: tx("Saldo", "Balance"), amount: item.remainingAmount)
                        FigureRow(label: tx("Pago recomendado este mes", "Recommended payment this month"), amount: item.recommendedPayment)
                        if let payoff = item.estimatedPayoffDate { InfoRow(label: tx("Saldada en", "Paid off by"), value: Day.label(payoff)) }
                    }
                    .accessibilityElement(children: .combine)
                }
                FigureRow(label: tx("Deuda total", "Total debt"), amount: plan.totalDebt)
                if let progress = plan.debtProgressPercent {
                    DincrProgressBar(fraction: progress / 100)
                    Text(tx("\(Int(progress.rounded()))% pagado", "\(Int(progress.rounded()))% paid")).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                }
                if let free = plan.estimatedDebtFreeDate { InfoRow(label: tx("Libre de deudas", "Debt-free"), value: Day.label(free)) }
                if plan.isOwnerScope, let saved = plan.monthsSavedByCurrentExtras, saved > 0 {
                    Text(tx("\(saved) meses antes gracias a los extras de este mes.", "\(saved) months sooner thanks to this month’s extras."))
                        .font(DincrFont.caption).foregroundStyle(DincrColor.positive)
                }
            }
            .dincrCard()
        }

        if let investment = plan.investmentRecommended, investment > 0 {
            FigureRow(label: tx("Inversión recomendada", "Recommended investment"), amount: investment).dincrCard()
        }

        if plan.isOwnerScope { OwnerStrategyFigures(plan: plan) }

        let rules = plan.rules ?? []
        if !rules.isEmpty {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                SectionHeader(title: tx("Reglas", "Rules"))
                ForEach(Array(rules.enumerated()), id: \.offset) { _, rule in
                    Label { Text(rule).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2) } icon: {
                        Image(systemName: "checkmark.circle").foregroundStyle(DincrColor.tint)
                    }
                }
            }
            .dincrCard()
        }
    }
}

/// The Owner's own cycle figures (historical JARVIS model). Rendered only for `scope == "owner"`.
private struct OwnerStrategyFigures: View {
    let plan: DashboardStrategy

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            SectionHeader(title: tx("Tu ciclo", "Your cycle"))
            FigureRow(label: tx("Ingreso recurrente", "Recurring income"), amount: plan.recurringMonthlyIncome)
            FigureRow(label: tx("Extras del mes (OT, bonos, feriados)", "This month’s extras (OT, bonuses, holidays)"), amount: plan.currentMonthExtraNet)
            FigureRow(label: tx("Ingreso recibido en el ciclo", "Income received this cycle"), amount: plan.incomeReceivedCurrentCycle)
            FigureRow(label: tx("Ingreso por recibir en el ciclo", "Income still to receive this cycle"), amount: plan.remainingIncomeCurrentCycle)
            FigureRow(label: tx("Efectivo distribuible", "Distributable cash"), amount: plan.distributableAccountCash)
            FigureRow(label: tx("Gastos del estado de cuenta", "Statement expenses"), amount: plan.statementExpenses)
            FigureRow(label: tx("Gastos nuevos después del corte", "New expenses after the cut"), amount: plan.newExpensesAfterCut)
            FigureRow(label: tx("Gastos fijos obligatorios pendientes", "Pending mandatory fixed expenses"), amount: plan.mandatoryFixedPending)
            ForEach(Array((plan.mandatoryFixedPendingItems ?? []).enumerated()), id: \.offset) { _, item in
                FigureRow(label: "· \(item.name ?? tx("Gasto fijo", "Fixed expense"))", amount: item.amount)
            }
        }
        .dincrCard()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("strategy.owner")
        if let portfolio = plan.investmentPortfolio {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                SectionHeader(title: tx("Portafolio de inversión", "Investment portfolio"))
                FigureRow(label: tx("Valor de mercado", "Market value"), amount: portfolio.marketValue, currency: portfolio.currency)
                FigureRow(label: tx("Capital aportado", "Contributed capital"), amount: portfolio.contributedCapital, currency: portfolio.currency)
                FigureRow(label: tx("Ganancia neta", "Net gain"), amount: portfolio.netPnl, currency: portfolio.currency)
            }
            .dincrCard()
        }
    }
}

private struct DistributionContent: View {
    let strategy: PlanStrategy

    var body: some View {
        switch strategy {
        case .basic(let basic):
            if basic.needsIncome {
                NeedsIncomeState(message: basic.recommendation)
            } else {
                if basic.usesObservedIncome { ObservedIncomeNote() }
                let allocations = basic.allocations ?? []
                VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                    SectionHeader(title: tx("Cómo repartir tu margen", "How to split your margin"))
                    FigureRow(label: tx("Margen para decidir", "Margin to decide"), amount: basic.strategicMargin)
                    if allocations.isEmpty {
                        Text(tx("Este mes no hay margen seguro para repartir.", "This month there is no safe margin to split."))
                            .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                    }
                    ForEach(Array(allocations.enumerated()), id: \.offset) { _, allocation in
                        FigureRow(label: allocation.label ?? allocation.bucket ?? "", amount: allocation.amount)
                    }
                }
                .dincrCard()
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier("distribution.basic")
            }
        case .dashboard(let dashboard):
            if let plan = dashboard.strategy {
                if plan.needsIncome {
                    NeedsIncomeState(message: plan.objective ?? dashboard.content)
                } else {
                    DashboardDistribution(plan: plan)
                }
            } else {
                EmptyStateView(symbol: "chart.pie", title: tx("Sin distribución por ahora", "No distribution for now"),
                               message: dashboard.content ?? tx("Volvé a intentarlo más tarde.", "Try again later.")) { EmptyView() }
            }
        }
    }
}

private struct DashboardDistribution: View {
    let plan: DashboardStrategy

    var body: some View {
        let items = plan.allocationItems ?? []
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Text(tx("Sobrante para repartir", "Surplus to allocate")).font(DincrFont.label).foregroundStyle(DincrColor.text2)
            MoneyText(plan.allocationBaseAmount, font: DincrFont.displayAmount)
            if items.isEmpty {
                Text(tx("Este mes no tiene sobrante real. Primero cubrí obligaciones y gastos registrados.",
                        "This month has no real surplus. Cover obligations and recorded expenses first."))
                    .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
            }
            ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                VStack(alignment: .leading, spacing: 4) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(DistributionLabels.bucket(item.key, targetName: item.targetName)).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text)
                        Spacer(minLength: DincrSpacing.s3)
                        if let percentage = item.percentage {
                            Text(String(format: "%.0f%%", percentage)).font(DincrFont.caption.monospacedDigit()).foregroundStyle(DincrColor.textMuted)
                        }
                        MoneyText(item.amount, font: DincrFont.amount)
                    }
                    DincrProgressBar(fraction: (item.percentage ?? 0) / 100)
                }
                .accessibilityElement(children: .combine)
            }
        }
        .dincrCard()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("distribution.dashboard")

        if let lines = plan.distributionFormula?.lines, !lines.isEmpty {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                SectionHeader(title: tx("De dónde sale", "Where it comes from"))
                ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                    FigureRow(label: DistributionLabels.formula(line.key), amount: line.amount)
                }
            }
            .dincrCard()
        }
    }
}

/// Labels of backend codes (presentation only).
enum StrategyText {
    static func emergencyLevel(_ level: String?) -> String? {
        switch level {
        case "mini_fund_building"?: tx("Construyendo tu mini fondo", "Building your mini fund")
        case "one_month_building"?: tx("Camino a 1 mes", "On the way to 1 month")
        case "three_month_building"?: tx("Camino a 3 meses", "On the way to 3 months")
        case "strong"?: tx("Sólido", "Strong")
        default: nil
        }
    }
}
