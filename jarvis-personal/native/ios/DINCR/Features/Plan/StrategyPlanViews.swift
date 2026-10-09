import DincrCore
import DincrDesign
import SwiftUI

/// UX-3 — "Tu plan del mes" (Plan tab): Estrategia and Distribución as one plan. Three contracts,
/// chosen from the server role and plan (`StrategySource`): Basic reads `/finance/strategy-basic`,
/// VIP Users `/vip/strategy-dashboard`, the Owner `/jarvis/premium/strategy-dashboard`. Every figure
/// is the backend's: first the amount to plan, how DINCR splits it and why in one sentence; the
/// derivation and every historical detail stay one tap away ("¿Por qué?", "Ver todo el detalle").
struct PlanStrategyView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ScreenScroll(title: tx("Tu plan del mes", "Your plan for the month")) {
            StrategyLoader { strategy in
                MonthPlanContent(strategy: strategy)
            }
            if model.planTier == .vip {
                // UX-7: the personal minimum (UX-8: the priority is DINCR's recommendation, not a setting).
                NavigationLink { PlanPreferencesView() } label: {
                    HubRow(symbol: "slider.horizontal.3", title: tx("Ajustes del plan", "Plan settings"),
                           subtitle: tx("Mínimo personal por mes", "Personal minimum per month"))
                }
                .buttonStyle(.plain)
                .dincrCard(padding: DincrSpacing.s3)
                .accessibilityIdentifier("plan.month.preferences")
            }
            OrganizeYourMonth()
            FinancialDisclaimer()
        }
    }
}

/// §15 PR 5 (option A) — "Para organizar tu mes": Presupuesto and Calendario financiero, the existing
/// screens, inside Tu plan del mes (Plan keeps its six entries). From Basic; §15 PR 10 (option A): Free
/// opens Tu plan del mes in its locked state and sees both here, locked, opening Suscripción.
private struct OrganizeYourMonth: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            SectionHeader(title: tx("Para organizar tu mes", "To organize your month"))
            if model.planTier.allows(.guidedBudget) {
                entry(symbol: "chart.pie", title: tx("Presupuesto", "Budget"), subtitle: tx("Límites por categoría", "Limits by category"),
                      id: "plan.month.budget") { BudgetView() }
                entry(symbol: "calendar", title: tx("Calendario financiero", "Financial calendar"),
                      subtitle: tx("Pagos e ingresos del mes", "Payments and income this month"), id: "plan.month.calendar") { CalendarView() }
            } else {
                entry(symbol: "chart.pie", title: tx("Presupuesto", "Budget"), subtitle: locked, id: "plan.month.budget", locked: true) { PlanSettingsView() }
                entry(symbol: "calendar", title: tx("Calendario financiero", "Financial calendar"), subtitle: locked,
                      id: "plan.month.calendar", locked: true) { PlanSettingsView() }
            }
        }
    }

    private var locked: String { tx("Disponible desde Basic", "Available from Basic") }

    private func entry<Destination: View>(symbol: String, title: String, subtitle: String, id: String, locked: Bool = false,
                                          @ViewBuilder destination: @escaping () -> Destination) -> some View {
        NavigationLink { destination() } label: { HubRow(symbol: symbol, title: title, subtitle: subtitle, locked: locked ? .basic : nil) }
            .buttonStyle(.plain)
            .dincrCard(padding: DincrSpacing.s3)
            .accessibilityIdentifier(id)
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
            // The same locked state as Android's: what the plan includes and the way to Suscripción.
            EmptyStateView(symbol: "lock", title: tx("Disponible desde Basic", "Available from Basic"),
                           message: tx("La estrategia y la distribución de tu dinero llegan con Basic.", "Strategy and money distribution come with Basic.")) {
                NavigationLink { PlanSettingsView() } label: { Text(tx("Ver suscripciones", "See subscriptions")) }
                    .buttonStyle(.dincrPrimary)
                    .accessibilityIdentifier("plan.month.subscriptions")
            }
        } else {
            AsyncContent(load: { try await model.service.planStrategy(source) }) { strategy, _ in
                content(strategy)
            }
            .id(source)
        }
    }
}

/// No income to plan with: ask for the declared income (never a strategy built on zero).
struct NeedsIncomeState: View {
    let message: String?

    var body: some View {
        EmptyStateView(symbol: "banknote", title: tx("Necesitamos tus ingresos", "We need your income"),
                       message: message ?? tx("Registrá tus ingresos o completá Ingresos y base para armar tu estrategia.",
                                              "Record your income or complete Income and base to build your strategy.")) {
            NavigationLink { IncomeBaseView() } label: { Text(tx("Completar ingresos y base", "Complete income and base")) }
                .buttonStyle(.dincrPrimary)
                .accessibilityIdentifier("strategy.completeIncomeBase")
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("strategy.needsIncome")
    }
}

/// The income is an estimate from recorded movements, not declared.
struct ObservedIncomeNote: View {
    var body: some View {
        StatusBanner(tone: .info, title: IncomeSourceLabel.observedNote(),
                     message: tx("Declará tu ingreso en Plan → Ingresos y base para una estrategia más precisa.",
                                 "Declare your income in Plan → Income and base for a more precise strategy."))
    }
}

private struct MonthPlanContent: View {
    let strategy: PlanStrategy

    var body: some View {
        if case .dashboard(let dashboard) = strategy, dashboard.strategy == nil {
            EmptyStateView(symbol: "map", title: tx("Sin plan todavía", "No plan yet"),
                           message: dashboard.content ?? tx("Volvé a intentarlo más tarde.", "Try again later.")) { EmptyView() }
        } else {
            let plan = MonthPlan(strategy)
            if plan.needsIncome {
                NeedsIncomeState(message: needsIncomeMessage)
            } else {
                if plan.usesObservedIncome { ObservedIncomeNote() }
                if plan.isCritical {
                    DincrMessage(.attention, title: plan.kind == .basic ? tx("Tus compromisos superan tus ingresos", "Your commitments exceed your income")
                                                                   : tx("Este mes no hay sobrante real", "No real surplus this month"),
                                 message: plan.criticalDetail ?? "")
                }
                // UX-8: DINCR's recommended priority and why (Basic and VIP; Free has no strategy).
                let recommended = RecommendedPriority.of(strategy)
                MonthPlanSummary(plan: plan, showsHeadline: recommended == nil)
                if let recommended { RecommendedPriorityCard(priority: recommended) }
                MonthPlanSplit(plan: plan)
                // Cautions stay in sight, never behind "¿Por qué?".
                if case .basic(let basic) = strategy {
                    ForEach(Array((basic.warnings ?? []).enumerated()), id: \.offset) { _, warning in
                        DincrMessage(.attention, title: tx("Tomá en cuenta", "Keep in mind"), message: warning)
                    }
                }
                // VIP (Users): the same cautions, and the way to complete a missing debt rate.
                if case .dashboard(let dashboard) = strategy, let detail = dashboard.strategy {
                    ForEach(Array((detail.warnings ?? []).enumerated()), id: \.offset) { _, warning in
                        DincrMessage(.attention, title: tx("Tomá en cuenta", "Keep in mind"), message: warning)
                    }
                    if detail.needsDebtRates {
                        NavigationLink { DebtsView() } label: {
                            HubRow(symbol: "creditcard", title: tx("Revisar deudas", "Review debts"),
                                   subtitle: tx("Completá las tasas de interés", "Add the interest rates"))
                        }
                        .buttonStyle(.plain)
                        .dincrCard(padding: DincrSpacing.s3)
                        .accessibilityIdentifier("plan.month.debtRates")
                    }
                }
                switch strategy {
                case .basic(let basic): BasicPlanDetail(strategy: basic)
                case .dashboard(let dashboard): if let detail = dashboard.strategy { DashboardPlanDetail(plan: detail) }
                }
            }
        }
    }

    private var needsIncomeMessage: String? {
        switch strategy {
        case .basic(let basic): basic.recommendation
        case .dashboard(let dashboard): dashboard.strategy?.objective ?? dashboard.content
        }
    }
}

/// The result first: the amount DINCR plans with and, in one sentence, what it recommends.
/// UX-8 — "Recomendación de DINCR": the priority the engine already recommends and why. It is not a
/// setting: the engines name one priority and no other option, so there is nothing to change here.
private struct RecommendedPriorityCard: View {
    let priority: RecommendedPriority

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Text(tx("Recomendación de DINCR", "DINCR’s recommendation")).font(DincrFont.label).foregroundStyle(DincrColor.text2)
            Text(priority.title).font(DincrFont.title2).foregroundStyle(DincrColor.text)
            if let why = priority.why { Text(why).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2) }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .dincrCard()
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("plan.month.recommendedPriority")
    }
}

private struct MonthPlanSummary: View {
    let plan: MonthPlan
    /// The headline says the same as the recommended priority, so it is left out when that is shown.
    var showsHeadline = true

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Text(plan.kind == .basic ? tx("Libre después de tus compromisos", "Left after your commitments") : tx("Sobrante para repartir", "Surplus to allocate"))
                .font(DincrFont.label).foregroundStyle(DincrColor.text2)
            MoneyText(plan.base, font: DincrFont.displayAmount)
            if showsHeadline, let headline = plan.summaryHeadline {
                Text(headline).font(DincrFont.body).foregroundStyle(DincrColor.text)
            }
        }
        .dincrCard()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(plan.kind == .basic ? "strategy.basic" : "strategy.dashboard")
    }
}

/// How DINCR splits the amount. A donut only when the parts exactly make up the amount
/// (`MonthPlan.showsComposition`); otherwise each part as the backend sent it.
private struct MonthPlanSplit: View {
    let plan: MonthPlan
    private var title: String { tx("Cómo DINCR lo reparte", "How DINCR splits it") }

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s3) {
            SectionHeader(title: title)
            if plan.parts.isEmpty {
                Text(plan.kind == .basic ? tx("Este mes no queda dinero libre para repartir.", "There’s no money left to split this month.")
                                         : tx("Este mes no hay sobrante real para repartir.", "There’s no real surplus to allocate this month."))
                    .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
            } else if plan.showsComposition {
                CompositionDonut(title: title, composition: plan.composition)
            } else {
                ForEach(plan.parts) { part in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(alignment: .firstTextBaseline) {
                            Text(part.label).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text)
                            Spacer(minLength: DincrSpacing.s3)
                            if let percentage = part.percentage {
                                Text(String(format: "%.0f%%", percentage)).font(DincrFont.caption.monospacedDigit()).foregroundStyle(DincrColor.textMuted)
                            }
                            MoneyText(part.amount, font: DincrFont.amount)
                        }
                        // The backend's own share, when it sent one; never a bar for an unknown share.
                        if part.percentage != nil { DincrProgressBar(ProgressValue(fraction: part.percentage.map { $0 / 100 })) }
                    }
                    .accessibilityElement(children: .combine)
                }
            }
        }
        .dincrCard()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("plan.month.split")
    }
}

/// Basic: the derivation and the rest of the strategy, one tap away.
private struct BasicPlanDetail: View {
    let strategy: Strategy
    @State private var expanded = false

    var body: some View {
        DisclosureGroup(isExpanded: $expanded) {
            VStack(alignment: .leading, spacing: DincrSpacing.s3) {
                StrategyContent(strategy: strategy, showsAllocations: false, showsRecommendation: false, showsWarnings: false)
                if let paycheck = strategy.nextPaycheck, let envelopes = paycheck.envelopes, !envelopes.isEmpty {
                    VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                        SectionHeader(title: tx("Tu próximo ingreso", "Your next paycheck"))
                        FigureRow(label: tx("Estimado", "Estimated"), amount: paycheck.estimatedPaycheck)
                        ForEach(Array(envelopes.enumerated()), id: \.offset) { _, envelope in
                            FigureRow(label: envelope.label ?? envelope.bucket ?? "", amount: envelope.amount)
                        }
                        if let unassigned = paycheck.unassigned, unassigned != 0 {
                            FigureRow(label: tx("Sin asignar", "Unassigned"), amount: unassigned)
                        }
                    }
                    .dincrCard()
                }
            }
            .padding(.top, DincrSpacing.s2)
        } label: {
            // The identifier goes on the label: on the group it would replace the identifiers inside.
            Text(tx("¿Por qué DINCR recomienda esto?", "Why does DINCR recommend this?")).font(DincrFont.label).foregroundStyle(DincrColor.tint)
                .accessibilityIdentifier("plan.month.why")
        }
        .tint(DincrColor.tint)
    }
}

/// VIP Users and the Owner: why (the priority's detail and where the amount comes from) and every
/// historical section, one tap away. Owner-only figures appear only when the backend sent the Owner
/// model (`scope == "owner"`); a Users answer never shows a cash balance.
private struct DashboardPlanDetail: View {
    let plan: DashboardStrategy
    @State private var showsWhy = false
    @State private var showsDetail = false

    var body: some View {
        DisclosureGroup(isExpanded: $showsWhy) {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                if let detail = plan.priority?.detail { Text(detail).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2) }
                if let lines = plan.distributionFormula?.lines, !lines.isEmpty {
                    SectionHeader(title: tx("De dónde sale", "Where it comes from"))
                    ForEach(Array(lines.enumerated()), id: \.offset) { _, line in
                        FigureRow(label: DistributionLabels.formula(line.key), amount: line.amount)
                    }
                }
            }
            .dincrCard()
            .padding(.top, DincrSpacing.s2)
        } label: {
            // The identifier goes on the label: on the group it would replace the identifiers inside.
            Text(tx("¿Por qué DINCR recomienda esto?", "Why does DINCR recommend this?")).font(DincrFont.label).foregroundStyle(DincrColor.tint)
                .accessibilityIdentifier("plan.month.why")
        }
        .tint(DincrColor.tint)

        DisclosureGroup(isExpanded: $showsDetail) {
            VStack(alignment: .leading, spacing: DincrSpacing.s3) { sections }
                .padding(.top, DincrSpacing.s2)
        } label: {
            Text(tx("Ver todo el detalle", "See full details")).font(DincrFont.label).foregroundStyle(DincrColor.tint)
                .accessibilityIdentifier("plan.month.detail")
        }
        .tint(DincrColor.tint)
    }

    @ViewBuilder private var sections: some View {
        if let title = plan.title, !title.isEmpty, let objective = plan.objective {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                Text(title).font(DincrFont.title2).foregroundStyle(DincrColor.text).accessibilityAddTraits(.isHeader)
                Text(objective).font(DincrFont.body).foregroundStyle(DincrColor.text2)
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
                // Unknown Users savings read as "Sin dato", never ₡0 (`emergencyKnown`).
                FigureRow(label: tx("Ahorro actual", "Current savings"), amount: plan.emergencyKnown ? fund.current : nil)
                FigureRow(label: tx("Base mensual", "Monthly base"), amount: fund.monthlyBase)
                FigureRow(label: tx("Próxima meta", "Next target"), amount: fund.nextTarget)
                // What is missing and the stage are measured from the savings: only when they are known.
                if plan.emergencyKnown {
                    FigureRow(label: tx("Te falta", "Still missing"), amount: fund.gapToNextTarget)
                    if let level = StrategyText.emergencyLevel(fund.level) { InfoRow(label: tx("Nivel", "Level"), value: level) }
                }
            }
            .dincrCard()
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("plan.month.salvavidas")
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
                    SectionHeader(title: tx("Cómo repartir lo que te queda", "How to split what’s left"))
                    FigureRow(label: tx("Libre después de tus compromisos", "Left after your commitments"), amount: basic.strategicMargin)
                    if allocations.isEmpty {
                        Text(tx("Este mes no queda dinero libre para repartir.", "There’s no money left to split this month."))
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
