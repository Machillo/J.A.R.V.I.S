import DincrCore
import DincrDesign
import SwiftUI

/// PARITY E11 — Salvavidas (VIP; the Owner by role), from `GET /vip/salvavidas`. The backend picks
/// the model from the server role: Users see months of their own obligations against the savings
/// they declared (unknown savings are "Sin dato", never "0 meses"); the Owner sees his historical
/// model with a manual balance and protected expenses. Coverage is never computed on the device.
struct SalvavidasView: View {
    @Environment(AppModel.self) private var model
    @State private var state: LoadState<Salvavidas> = .loading
    @State private var generation = 0
    @State private var saving = false
    @State private var error: String?
    @State private var notice: String?
    @State private var editingAmount = false

    var body: some View {
        ScreenScroll(title: "Salvavidas") {
            WritesPausedBanner()
            if let notice { StatusBanner(tone: .info, title: notice, message: "").accessibilityIdentifier("salvavidas.notice") }
            if let error { ErrorStateView(message: error) }
            switch state {
            case .loading:
                SkeletonView(rows: 3)
            case .failed(let message):
                ErrorStateView(message: message) { generation += 1 }
            case .loaded(let fund):
                if fund.isOwnerScope {
                    OwnerSalvavidasContent(fund: fund, canWrite: canWrite, saving: saving,
                                           setTarget: { months in Task { await save(.target(months: months)) } },
                                           editAmount: { editingAmount = true },
                                           toggle: { ids in Task { await save(.protectedExpenses(ids)) } },
                                           savePlan: { update in await save(update) })
                } else {
                    UsersSalvavidasContent(fund: fund, canWrite: canWrite, saving: saving,
                                           setTarget: { months in Task { await save(.target(months: months)) } },
                                           editAmount: { editingAmount = true },
                                           savePlan: { update in await save(update) })
                }
            }
            FinancialDisclaimer()
        }
        .task(id: generation) { await load() }
        .sheet(isPresented: $editingAmount) {
            SavingsAmountSheet(current: currentAmount) { amount in
                await save(.currentAmount(amount))
            }
        }
    }

    private var canWrite: Bool { model.flags.isEnabled(.financialWrites) }

    private var currentAmount: Decimal? {
        if case .loaded(let fund) = state, fund.savingsKnown { return fund.currentAmount }
        return nil
    }

    private func load() async {
        let epoch = model.currentEpoch
        do {
            let fund = try await model.service.salvavidas()
            if epoch == model.currentEpoch { state = .loaded(fund) }
        } catch is CancellationError {
            return
        } catch {
            if let message = model.message(for: error, epoch: epoch, fallback: tx("No pudimos cargar tu Salvavidas.", "We couldn’t load your emergency fund.")) {
                state = .failed(message)
            }
        }
    }

    /// One change; the screen shows the backend's answer (never a figure computed here). Returns an
    /// error message for the amount sheet, or nil when saved.
    @discardableResult
    private func save(_ update: SalvavidasUpdate) async -> String? {
        guard !saving else { return nil }
        saving = true; error = nil; notice = nil
        defer { saving = false }
        let epoch = model.currentEpoch
        do {
            let fund = try await model.service.updateSalvavidas(update)
            guard epoch == model.currentEpoch else { return nil }
            state = .loaded(fund)
            notice = tx("Salvavidas actualizado", "Emergency fund updated")
            return nil
        } catch {
            let message = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardar.", "We couldn’t save."))
            self.error = message
            return message
        }
    }
}

/// The 1/3/6-month goal as the backend allows it.
private struct TargetPicker: View {
    let fund: Salvavidas
    let enabled: Bool
    let setTarget: (Int) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Text(tx("Meta de cobertura", "Coverage goal")).font(DincrFont.label).foregroundStyle(DincrColor.text2)
            Picker(tx("Meta de cobertura", "Coverage goal"), selection: Binding(get: { fund.targetMonths ?? 6 }, set: { months in
                if months != fund.targetMonths { setTarget(months) }
            })) {
                ForEach(fund.targetChoices, id: \.self) { months in
                    Text(tx("\(months) \(months == 1 ? "mes" : "meses")", "\(months) \(months == 1 ? "month" : "months")")).tag(months)
                }
            }
            .pickerStyle(.segmented)
            .disabled(!enabled)
            .accessibilityIdentifier("salvavidas.target")
        }
    }
}

/// Coverage, progress and goal. Unknown savings say "Sin dato" (never zero coverage).
private struct CoverageCard: View {
    let fund: Salvavidas

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Text(tx("Tu Salvavidas cubre", "Your emergency fund covers")).font(DincrFont.label).foregroundStyle(DincrColor.text2)
            Text(fund.coverageLabel()).font(DincrFont.displayAmount).foregroundStyle(DincrColor.text)
                .accessibilityIdentifier("salvavidas.coverage")
            if fund.savingsKnown {
                // With automatic contributions on, the balance is an estimate following the plan.
                FigureRow(label: fund.activePlan == nil ? tx("Ahorro actual", "Current savings") : tx("Ahorro estimado", "Estimated savings"),
                          amount: fund.currentAmount)
                SalvavidasPlanBreakdown(fund: fund)
            } else {
                InfoRow(label: tx("Ahorro actual", "Current savings"), value: tx("Sin dato", "No data"))
            }
            FigureRow(label: tx("Obligaciones por mes", "Obligations per month"), amount: fund.monthlyBase)
            FigureRow(label: tx("Meta", "Target"), amount: fund.targetAmount)
            if fund.savingsKnown {
                FigureRow(label: tx("Te falta", "Still missing"), amount: fund.missingAmount)
                if let progress = fund.progressPercent { DincrProgressBar(fraction: progress / 100) }
            }
        }
        .dincrCard()
    }
}

private struct UsersSalvavidasContent: View {
    let fund: Salvavidas
    let canWrite: Bool
    let saving: Bool
    let setTarget: (Int) -> Void
    let editAmount: () -> Void
    let savePlan: (SalvavidasUpdate) async -> String?

    var body: some View {
        if fund.needsObligations {
            EmptyStateView(symbol: "lifepreserver", title: tx("Todavía no hay obligaciones", "No obligations yet"),
                           message: tx("Tu Salvavidas se mide en meses de tus deudas y pagos recurrentes. Agregá tus deudas o tus pagos recurrentes para calcularlo.",
                                       "Your emergency fund is measured in months of your debts and recurring payments. Add your debts or recurring payments to calculate it.")) { EmptyView() }
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier("salvavidas.needsObligations")
        } else {
            CoverageCard(fund: fund)
            VStack(alignment: .leading, spacing: DincrSpacing.s3) {
                TargetPicker(fund: fund, enabled: canWrite && !saving, setTarget: setTarget)
                if canWrite {
                    Button(tx("Actualizar ahorros", "Update savings"), action: editAmount)
                        .buttonStyle(.dincrSecondary)
                        .disabled(saving)
                        .accessibilityIdentifier("salvavidas.updateSavings")
                }
                if !fund.savingsKnown {
                    Text(tx("Declará tus ahorros en Metas y ahorro → Tus ahorros para medir cuántos meses te cubren.",
                            "Declare your savings in Goals and savings → Your savings to measure how many months they cover."))
                        .font(DincrFont.caption).foregroundStyle(DincrColor.text2)
                    NavigationLink { DeclaredSavingsView() } label: { Text(tx("Completar tus ahorros", "Complete your savings")) }
                        .buttonStyle(.dincrPrimary)
                        .accessibilityIdentifier("salvavidas.completeSavings")
                }
            }
            .dincrCard()
            AutoContributionCard(fund: fund, canWrite: canWrite, saving: saving, save: savePlan)
        }
        SalvavidasDetails { ObligationLines(fund: fund) }
    }
}

/// The Owner: coverage, goal and balance, the contribution plan, and the detail (what is protected,
/// debts, milestones) folded away so the screen opens with what matters.
private struct OwnerSalvavidasContent: View {
    let fund: Salvavidas
    let canWrite: Bool
    let saving: Bool
    let setTarget: (Int) -> Void
    let editAmount: () -> Void
    let toggle: ([Int]) -> Void
    let savePlan: (SalvavidasUpdate) async -> String?

    var body: some View {
        CoverageCard(fund: fund)
        VStack(alignment: .leading, spacing: DincrSpacing.s3) {
            TargetPicker(fund: fund, enabled: canWrite && !saving, setTarget: setTarget)
            if canWrite {
                Button(tx("Editar saldo", "Edit balance"), action: editAmount)
                    .buttonStyle(.dincrSecondary)
                    .disabled(saving)
                    .accessibilityIdentifier("salvavidas.editBalance")
            }
        }
        .dincrCard()
        AutoContributionCard(fund: fund, canWrite: canWrite, saving: saving, save: savePlan)
        SalvavidasDetails {
            let available = fund.availableExpenses ?? []
            if !available.isEmpty {
                Text(tx("Gastos que querés proteger", "Expenses you want to protect")).font(DincrFont.label).foregroundStyle(DincrColor.text2)
                ForEach(available) { expense in
                    Toggle(isOn: Binding(get: { expense.selected == true }, set: { on in
                        guard let id = expense.lineId else { return }
                        var ids = Set(fund.protectedExpenseIds ?? [])
                        if on { ids.insert(id) } else { ids.remove(id) }
                        toggle(Array(ids))
                    })) {
                        HStack {
                            Text(expense.name ?? tx("Gasto", "Expense")).font(DincrFont.bodySmall)
                            Spacer()
                            MoneyText(expense.monthlyAmount, font: DincrFont.bodySmall.monospacedDigit())
                        }
                    }
                    .tint(DincrColor.tint)
                    .disabled(!canWrite || saving)
                    .accessibilityIdentifier("salvavidas.protect.\(expense.lineId ?? 0)")
                }
            }
            ObligationLines(fund: fund)
        }
    }
}

/// "Qué cubre tu Salvavidas", closed by default: the detail behind the monthly base.
private struct SalvavidasDetails<Content: View>: View {
    @ViewBuilder let content: () -> Content
    @State private var expanded = false

    var body: some View {
        DisclosureGroup(isExpanded: $expanded) {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) { content() }
                .padding(.top, DincrSpacing.s2)
        } label: {
            Text(tx("Qué cubre tu Salvavidas", "What your emergency fund covers")).font(DincrFont.label).foregroundStyle(DincrColor.text)
                .frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityIdentifier("salvavidas.details")
        }
        .tint(DincrColor.tint)
        .dincrCard()
    }
}

/// What the monthly base is made of: debt payments and recurring payments, and the milestones.
private struct ObligationLines: View {
    let fund: Salvavidas

    var body: some View {
        Lines(title: tx("Cuotas de deudas", "Debt payments"), lines: fund.debts ?? [])
        Lines(title: tx("Pagos recurrentes", "Recurring payments"), lines: fund.obligations ?? [])
        let milestones = fund.milestones ?? []
        if !milestones.isEmpty {
            Text(tx("Hitos", "Milestones")).font(DincrFont.label).foregroundStyle(DincrColor.text2)
            ForEach(Array(milestones.enumerated()), id: \.offset) { _, milestone in
                HStack {
                    Image(systemName: milestone.reached == true ? "checkmark.circle.fill" : "circle")
                        .foregroundStyle(milestone.reached == true ? DincrColor.positive : DincrColor.textMuted)
                        .accessibilityHidden(true)
                    let months = milestone.months ?? 0
                    Text(tx("\(months) \(months == 1 ? "mes" : "meses")", "\(months) \(months == 1 ? "month" : "months")")).font(DincrFont.bodySmall)
                    Spacer()
                    MoneyText(milestone.target, font: DincrFont.bodySmall.monospacedDigit())
                }
                .accessibilityElement(children: .combine)
                .accessibilityValue(milestone.reached == true ? tx("alcanzado", "reached") : tx("pendiente", "pending"))
            }
        }
    }
}

private struct Lines: View {
    let title: String
    let lines: [Salvavidas.Line]

    var body: some View {
        if !lines.isEmpty {
            Text(title).font(DincrFont.label).foregroundStyle(DincrColor.text2)
            ForEach(lines) { line in
                FigureRow(label: line.name ?? "—", amount: line.monthlyAmount)
            }
        }
    }
}

/// The fund's balance: the Owner's manual balance, or the user's declared savings (the same field as
/// the financial situation). Returns an error to show, or nil when saved.
private struct SavingsAmountSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let current: Decimal?
    let submit: (Decimal) async -> String?
    @State private var text = ""
    @State private var error: String?
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    MoneyField(label: tx("Ahorro disponible", "Available savings"), text: $text, error: error, identifier: "salvavidas.amount")
                } footer: {
                    Text(tx("Lo que tenés hoy en la cuenta, incluido el aporte que ya entró hoy. Es el mismo dato de Metas y ahorro → Tus ahorros.",
                            "What the account holds today, including a contribution that already arrived today. It’s the same figure as in Goals and savings → Your savings."))
                }
            }
            .navigationTitle(tx("Ahorros", "Savings"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(tx("Cancelar", "Cancel")) { dismiss() }.disabled(saving) }
                ToolbarItem(placement: .confirmationAction) {
                    Button(tx("Guardar", "Save")) { Task { await save() } }.disabled(saving).accessibilityIdentifier("salvavidas.amount.save")
                }
            }
            .onAppear { if text.isEmpty, let current { text = model.moneyFormat.inputText(current) } }
        }
        .presentationDetents([.medium])
        .interactiveDismissDisabled(saving)
    }

    private func save() async {
        guard let amount = AmountInput.parseZeroOrMore(text, separators: model.moneyFormat.separators) else {
            error = model.moneyFormat.amountHint; return
        }
        saving = true; error = nil
        let failure = await submit(amount)
        saving = false
        if let failure { error = failure } else { dismiss() }
    }
}
