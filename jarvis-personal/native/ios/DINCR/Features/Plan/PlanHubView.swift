import DincrCore
import DincrDesign
import SwiftUI

/// PARITY E1 — the Plan tab: exactly five rows, in this order (`PlanHubItem`): Aguinaldo,
/// Tu plan del mes (UX-3: Estrategia + Distribución as one plan; the row keeps the Estrategia
/// identifier and gate), Deudas (UX-4: where debts are managed, every plan; Home keeps a shortcut),
/// Salvavidas and Distribución de dinero (kept as a transitional access until its retirement is
/// approved). A row the plan does not include stays visible, locked ("Disponible desde Basic/VIP"),
/// and opens the plans screen; a row paused by an operational switch says so. Goals are on Home;
/// budget, calendar and recurring items in Profile → Finanzas.
struct PlanHubView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ScreenScroll(title: tx("Plan", "Plan")) {
            VStack(spacing: DincrSpacing.s2) {
                ForEach(PlanHubItem.allCases) { item in
                    row(item)
                }
            }
        }
    }

    @ViewBuilder
    private func row(_ item: PlanHubItem) -> some View {
        let availability = item.availability(tier: model.planTier, flags: model.flags)
        switch availability {
        case .available:
            NavigationLink { destination(item) } label: { HubRow(symbol: item.symbol, title: item.title, subtitle: item.subtitle) }
                .buttonStyle(.plain)
                .dincrCard(padding: DincrSpacing.s3)
                .accessibilityIdentifier("plan.\(item.rawValue)")
        case .locked(let tier):
            NavigationLink { PlanSettingsView() } label: {
                HubRow(symbol: item.symbol, title: item.title,
                       subtitle: tx("Disponible desde \(PlanLabel.name(tier.rawValue))", "Available from \(PlanLabel.name(tier.rawValue))"), locked: tier)
            }
            .buttonStyle(.plain)
            .dincrCard(padding: DincrSpacing.s3)
            .accessibilityIdentifier("plan.\(item.rawValue)")
            .accessibilityHint(tx("Abre los planes", "Opens the plans"))
        case .paused(let flag):
            NavigationLink {
                ScreenScroll(title: item.title) { FeaturePausedView(message: model.flags.message(flag, language: model.language)) }
            } label: {
                HubRow(symbol: item.symbol, title: item.title, subtitle: tx("En pausa por mantenimiento", "Paused for maintenance"))
            }
            .buttonStyle(.plain)
            .dincrCard(padding: DincrSpacing.s3)
            .accessibilityIdentifier("plan.\(item.rawValue)")
        }
    }

    @ViewBuilder
    private func destination(_ item: PlanHubItem) -> some View {
        switch item {
        case .aguinaldo: AguinaldoView()
        case .strategy: PlanStrategyView()
        case .debts: DebtsView()
        case .salvavidas: SalvavidasView()
        case .distribution: DistributionView()
        }
    }
}

extension PlanHubItem {
    var title: String {
        switch self {
        case .aguinaldo: tx("Aguinaldo", "Aguinaldo")
        case .strategy: tx("Tu plan del mes", "Your plan for the month")
        case .debts: tx("Deudas", "Debts")
        case .salvavidas: "Salvavidas"
        case .distribution: tx("Distribución de dinero", "Money distribution")
        }
    }

    var subtitle: String {
        switch self {
        case .aguinaldo: tx("Estimado según tus salarios", "Estimated from your salaries")
        case .strategy: tx("Cuánto podés repartir y cómo", "How much you can split, and how")
        case .debts: tx("Saldos, cuotas y pagos", "Balances, payments")
        case .salvavidas: tx("Cuántos meses de obligaciones te cubre", "How many months of obligations it covers")
        case .distribution: tx("Cómo repartir tu sobrante del mes", "How to split this month’s surplus")
        }
    }

    var symbol: String {
        switch self {
        case .aguinaldo: "gift"
        case .strategy: "map"
        case .debts: "creditcard"
        case .salvavidas: "lifepreserver"
        case .distribution: "chart.pie"
        }
    }
}

/// B5 — writes paused by the operational switch: shown where money can be written.
struct WritesPausedBanner: View {
    @Environment(AppModel.self) private var model
    var body: some View {
        if !model.flags.isEnabled(.financialWrites) {
            DincrMessage(.technicalError, title: tx("Cambios temporalmente pausados", "Changes temporarily paused"),
                         message: model.flags.message(.financialWrites, language: model.language)
                            ?? tx("Podés ver tu información; guardar cambios está en pausa por mantenimiento.", "You can see your information; saving changes is paused for maintenance."))
        }
    }
}

enum AmountAction: Identifiable {
    case payDebt(Debt)
    case contribute(Goal)
    case save(SavingsPlan)

    var id: String {
        switch self {
        case .payDebt(let debt): "debt-\(debt.id)"
        case .contribute(let goal): "goal-\(goal.id)"
        case .save(let plan): "savings-\(plan.id)"
        }
    }
}

/// One amount, typed in the user's own separators. Retrying the same amount after an error reuses
/// its idempotency key, so a lost response never records the money twice.
struct AmountSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let action: AmountAction
    let onDone: (String) -> Void
    @State private var text = ""
    @State private var error: String?
    @State private var saving = false
    @State private var submission = AmountSubmission()

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text(explanation).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                    TextField(tx("Monto", "Amount"), text: $text)
                        .keyboardType(.decimalPad)
                        .accessibilityIdentifier("amount.field")
                    if let error {
                        Text(error).font(DincrFont.caption).foregroundStyle(DincrColor.negative)
                    }
                }
            }
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(tx("Cancelar", "Cancel")) { dismiss() }.disabled(saving)
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(confirm) { Task { await submit() } }
                        .disabled(saving)
                        .accessibilityIdentifier("amount.save")
                }
            }
        }
        .presentationDetents([.medium])
        .interactiveDismissDisabled(saving)
    }

    private var title: String {
        switch action {
        case .payDebt: tx("Registrar pago", "Record payment")
        case .contribute(let goal): tx("Aportar a «\(goal.name ?? "")»", "Contribute to “\(goal.name ?? "")”")
        case .save(let plan): tx("Aportar a «\(plan.name ?? "")»", "Contribute to “\(plan.name ?? "")”")
        }
    }

    private var confirm: String {
        switch action {
        case .payDebt: tx("Registrar", "Record")
        case .contribute, .save: tx("Aportar", "Contribute")
        }
    }

    private var explanation: String {
        let format = model.moneyFormat
        switch action {
        case .payDebt(let debt):
            let remaining = format.string(debt.remainingAmount ?? 0)
            return tx("Pendiente: \(remaining). Un pago mayor se ajusta al saldo.", "Outstanding: \(remaining). A larger payment is capped at the balance.")
        case .contribute(let goal):
            let remaining = goal.remaining.map { format.string($0) } ?? "—"
            return tx("Faltan \(remaining). Un aporte mayor se ajusta a la meta.", "\(remaining) to go. A larger amount is capped at the goal.")
        case .save(let plan):
            return tx("Ahorrado: \(format.string(plan.savedAmount ?? 0)).", "Saved: \(format.string(plan.savedAmount ?? 0)).")
        }
    }

    private func submit() async {
        guard !saving else { return }
        guard let amount = AmountInput.parse(text, separators: model.moneyFormat.separators) else {
            error = model.moneyFormat.amountHint
            return
        }
        let key = submission.key(for: amount)
        saving = true; error = nil
        defer { saving = false }
        let epoch = model.currentEpoch
        do {
            switch action {
            case .payDebt(let debt):
                _ = try await model.service.payDebt(id: debt.id, amount: amount, idempotencyKey: key)
                onDone(tx("Pago registrado", "Payment recorded"))
            case .contribute(let goal):
                _ = try await model.service.contribute(goalID: goal.id, GoalContribution(amount: amount, contributionDate: Day.today()), idempotencyKey: key)
                onDone(tx("Aporte registrado", "Contribution recorded"))
            case .save(let plan):
                _ = try await model.service.contribute(savingsPlanID: plan.id, GoalContribution(amount: amount, contributionDate: Day.today()), idempotencyKey: key)
                onDone(tx("Aporte registrado", "Contribution recorded"))
            }
            dismiss()
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardar. Intentá de nuevo.", "We couldn’t save. Please try again."))
        }
    }
}
