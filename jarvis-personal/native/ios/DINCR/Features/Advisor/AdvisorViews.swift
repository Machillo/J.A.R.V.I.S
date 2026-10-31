import DincrCore
import DincrDesign
import SwiftUI

/// UX-13 — Movimientos → Análisis: the monthly summary (every plan) and, FA-1, the financial analysis
/// in plain words (VIP and the Owner; below VIP the row stays visible, locked, and opens Suscripción).
/// The Owner's full historical analysis stays in JARVIS → Análisis financiero.
struct AnalysisHubView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ScreenScroll(title: tx("Análisis", "Analysis")) {
            VStack(spacing: DincrSpacing.s2) {
                GatedEntry(minimum: .free, flag: nil, symbol: "calendar.badge.checkmark", title: tx("Resumen del mes", "Monthly summary"),
                           subtitle: tx("Ingresos, gastos y categorías", "Income, expenses and categories"), id: "analysis.summary") { MonthlySummaryView() }
                GatedEntry(minimum: .vip, flag: nil, symbol: "chart.pie", title: tx("Análisis financiero", "Financial analysis"),
                           subtitle: tx("Tus números explicados en palabras simples", "Your numbers explained in simple words"),
                           id: "analysis.financial") { FinancialAnalysisView() }
            }
        }
    }
}

/// UX-13 / §15 PR 8 — the Patrimonio tab. Cuentas: the accounts DINCR detected in bank notices and
/// the mail connections that read them (the existing screens; VIP and the Owner, locked below).
/// Deudas: how the active debts make up what is owed, from Plan → Deudas' balances (every plan).
/// Proyecciones and Escenarios (VIP). No net worth figure until P0.9 (K-3), no balance invented.
/// B17: pulling down reads the plan, the switches and the debts again; a failed read keeps what the
/// card showed (`PullRefresh`).
struct WealthHubView: View {
    @Environment(AppModel.self) private var model
    @State private var debts: LoadState<[Debt]> = .loading

    var body: some View {
        ScreenScroll(title: tx("Patrimonio", "Wealth")) {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                SectionHeader(title: tx("Cuentas", "Accounts"))
                // The screens say themselves when the mail switch pauses them (as in Perfil).
                GatedEntry(minimum: .vip, flag: nil, symbol: "building.columns", title: tx("Cuentas", "Accounts"),
                           subtitle: tx("Bancos y cuentas detectados en tus avisos", "Banks and accounts found in your notices"), id: "wealth.accounts") { AccountsView() }
                // Reading mail is the Owner's alone during the launch: no row, not even locked, for anyone else.
                if model.canReadMail {
                    GatedEntry(minimum: .vip, flag: nil, symbol: "envelope", title: tx("Conexiones de correo", "Mail connections"),
                               subtitle: tx("Correo conectado, permisos y buscar avisos", "Connected mail, permissions and checking for notices"), id: "wealth.connections") { EmailMonitorView() }
                }
                SectionHeader(title: tx("Deudas", "Debts"))
                WealthDebtsCard(debts: debts) { Task { await loadDebts(refreshing: false) } }
                SectionHeader(title: tx("Proyecciones", "Projections"))
                GatedEntry(minimum: .vip, flag: .vipIntelligence, symbol: "chart.line.uptrend.xyaxis", title: tx("Proyecciones", "Projections"),
                           subtitle: tx("Tus próximos meses", "Your next months"), id: "wealth.projections") { ProjectionsView() }
                GatedEntry(minimum: .vip, flag: .vipIntelligence, symbol: "slider.horizontal.3", title: tx("Escenarios", "Scenarios"),
                           subtitle: tx("¿Y si gano o gasto distinto?", "What if I earn or spend differently?"), id: "wealth.scenarios") { ScenariosView() }
            }
        }
        .task { await loadDebts(refreshing: false) }
        .refreshable { await model.refreshTab { await loadDebts(refreshing: true) } }
    }

    /// Returns whether the debts were read. A refresh that fails keeps the debts already shown.
    private func loadDebts(refreshing: Bool) async -> Bool {
        let epoch = model.currentEpoch
        let current: [Debt]? = if case .loaded(let value) = debts { value } else { nil }
        do {
            let value = try await model.service.debts()
            if epoch == model.currentEpoch { debts = .loaded(value) }
            return true
        } catch is CancellationError {
            return true
        } catch {
            let message = model.message(for: error, epoch: epoch, fallback: tx("No pudimos cargar esta información.", "We couldn’t load this information."))
            if refreshing, let kept = PullRefresh.kept(current, after: .failure(error)) {
                debts = .loaded(kept)
            } else if let message {
                debts = .failed(message)
            }
            return false
        }
    }
}

/// §15 PR 8 — what is owed, by debt, from the balances in Plan → Deudas (`DebtComposition`); managed
/// there. An unknown balance is listed as unknown and no share or total is drawn from it.
private struct WealthDebtsCard: View {
    let debts: LoadState<[Debt]>
    let retry: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            switch debts {
            case .loading:
                SkeletonView(rows: 3)
            case .failed(let message):
                ErrorStateView(message: message, retry: retry)
            case .loaded(let debts):
                let composition = DebtComposition.of(debts)
                if composition.status == .empty {
                    Text(tx("No tenés deudas activas registradas.", "You have no active debts recorded."))
                        .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                        .accessibilityIdentifier("wealth.debts.none")
                } else {
                    CompositionDonut(title: tx("Lo que debés, por deuda", "What you owe, by debt"), composition: composition)
                        .accessibilityIdentifier("wealth.debts.composition")
                }
            }
            NavigationLink { DebtsView() } label: {
                Text(tx("Administrar en Plan › Deudas", "Manage in Plan › Debts")).font(DincrFont.bodySmall.weight(.semibold))
                    .foregroundStyle(DincrColor.tint).frame(minHeight: 44)
            }
            .accessibilityIdentifier("wealth.debts.manage")
        }
        .dincrCard()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("wealth.debts")
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

/// PARITY D7 — Resumen (Free and up), simple on purpose: a month or a whole year, what came in and
/// went out, what was saved (money put aside, never income minus spending), and two donuts: where
/// the money came from and where it went. Every figure is the backend's
/// (`/free/monthly-summary?period=YYYY-MM|YYYY`). The Owner's ledger detail stays one tap away.
struct MonthlySummaryView: View {
    @Environment(AppModel.self) private var model
    @State private var yearly = false
    @State private var period = Period.current
    @State private var year = String(Period.current.prefix(4))

    private var selected: String { yearly ? year : period }

    var body: some View {
        ScreenScroll(title: tx("Resumen del mes", "Monthly summary")) {
            Picker(tx("Periodo", "Period"), selection: $yearly) {
                Text(tx("Mes", "Month")).tag(false)
                Text(tx("Año", "Year")).tag(true)
            }
            .pickerStyle(.segmented)
            .accessibilityIdentifier("summary.scope")
            if yearly { YearPicker(year: $year) } else { MonthPicker(period: $period) }
            AsyncContent(load: { try await model.service.monthlySummary(period: selected) }) { summary, _ in
                SummaryContent(summary: summary)
            }
            .id(selected)
        }
    }
}

private struct SummaryContent: View {
    let summary: MonthlySummary

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            FigureRow(label: tx("Ingresos", "Income"), amount: summary.income, sign: .income)
                .accessibilityIdentifier("summary.income")
            FigureRow(label: tx("Gastos", "Expenses"), amount: summary.expenses, sign: .expense)
                .accessibilityIdentifier("summary.expenses")
            if let debt = summary.debtPaid, debt > 0 {
                FigureRow(label: tx("Pagos de deudas", "Debt payments"), amount: debt)
            }
            FigureRow(label: tx("Lo que guardaste", "What you saved"), amount: summary.saved?.total)
                .accessibilityIdentifier("summary.saved")
            if let saved = summary.saved, (saved.goals ?? 0) > 0 || (saved.salvavidas ?? 0) > 0 {
                SavedBreakdown(saved: saved)
            }
            if let notice = SummaryVisuals.flowNotice(SummaryVisuals.flow(summary)) {
                Text(notice).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                    .accessibilityIdentifier("summary.flow.notice")
            }
        }
        .dincrCard()
        if summary.isOwnerLedger { OwnerLedgerDetail(summary: summary) }
        VStack(alignment: .leading, spacing: DincrSpacing.s3) {
            SectionHeader(title: tx("¿De dónde entró?", "Where did it come from?"))
            CompositionDonut(title: tx("Ingresos por categoría", "Income by category"), composition: SummaryVisuals.incomeSources(summary),
                             color: DincrColor.chartIncome, showsTotal: false)
        }
        .dincrCard()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("summary.incomeSources")
        VStack(alignment: .leading, spacing: DincrSpacing.s3) {
            SectionHeader(title: tx("¿A dónde se fue?", "Where did it go?"))
            CompositionDonut(title: tx("Gastos, deudas y ahorro", "Spending, debts and savings"), composition: SummaryVisuals.outflows(summary),
                             color: DincrColor.chartExpense, showsTotal: false)
        }
        .dincrCard()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("summary.categories")
    }
}

/// "A metas ₡X · Al Salvavidas ₡Y": where the saved money went.
private struct SavedBreakdown: View {
    @Environment(AppModel.self) private var model
    let saved: MonthlySummary.Saved

    var body: some View {
        let format = model.moneyFormat
        let parts = [
            (saved.goals ?? 0) > 0 ? tx("A metas \(format.string(saved.goals ?? 0))", "To goals \(format.string(saved.goals ?? 0))") : nil,
            (saved.salvavidas ?? 0) > 0 ? tx("Al Salvavidas \(format.string(saved.salvavidas ?? 0))", "To your emergency fund \(format.string(saved.salvavidas ?? 0))") : nil,
        ].compactMap { $0 }
        Text(parts.joined(separator: " · ")).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            .accessibilityIdentifier("summary.saved.breakdown")
    }
}

/// The Owner: a short line when the period still has things to review (its figures may change),
/// and the ledger's full reading one tap away (OwnerReadingViews.swift).
private struct OwnerLedgerDetail: View {
    let summary: MonthlySummary
    @State private var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            if summary.complete == false {
                Label(tx("Todavía hay cosas por revisar: estas cifras pueden cambiar.", "There are still things to review: these figures may change."),
                      systemImage: "exclamationmark.circle")
                    .font(DincrFont.caption).foregroundStyle(DincrColor.warning)
                    .accessibilityIdentifier("summary.owner.incomplete")
            }
            DisclosureGroup(isExpanded: $expanded) {
                OwnerMonthSummary(summary: summary).padding(.top, DincrSpacing.s2)
            } label: {
                Text(tx("Ver el detalle", "See the detail")).font(DincrFont.label).foregroundStyle(DincrColor.text)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityIdentifier("summary.owner.detail")
            }
            .tint(DincrColor.tint)
        }
        .dincrCard()
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
            FigureRow(label: tx("Libre después de tus compromisos", "Left after your commitments"), amount: strategy.strategicMargin)
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
    @State private var choice: ScenarioChoice = .general

    var body: some View {
        ScreenScroll(title: tx("Escenarios", "Scenarios")) {
            ScenarioChoicePicker(choice: $choice)
            if choice == .general { general } else { DebtScenarioForm(choice: choice).id(choice) }
            FinancialDisclaimer()
        }
    }

    /// Income, expense and one-off changes (the original what-if).
    @ViewBuilder private var general: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s3) {
            Text(tx("Probá cambios sin guardar nada: DINCR calcula cuánto te quedaría libre cada mes. Usá − para una baja.", "Try changes without saving anything: DINCR shows how much you’d have left each month. Use − for a decrease."))
                .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
            MoneyField(label: tx("Cambio mensual de ingresos", "Monthly income change"), text: $income)
            MoneyField(label: tx("Cambio mensual de gastos", "Monthly expense change"), text: $expenses)
            MoneyField(label: tx("Dinero extra único", "One-off extra money"), text: $extra)
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
                FigureRow(label: tx("Te queda libre al mes hoy", "Left each month today"), amount: result.current?.strategicMargin)
                FigureRow(label: tx("Te quedaría libre con el cambio", "Left each month with the change"), amount: result.scenario?.strategicMargin)
                FigureRow(label: tx("Diferencia", "Difference"), amount: result.delta?.strategicMargin)
            }
            .dincrCard()
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
