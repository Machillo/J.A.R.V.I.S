import DincrCore
import DincrDesign
import SwiftUI

/// PARITY E1–E7 — debts and goals: see balances and record payments and contributions. Balances
/// are the backend's; the app sends only the amount the user typed (with an idempotency key, so a
/// retried submit is never a second payment) and reloads what the server answers.
struct PlanHubView: View {
    @Environment(AppModel.self) private var model
    @State private var state: LoadState<Snapshot> = .loading
    @State private var action: AmountAction?
    @State private var notice: String?

    struct Snapshot: Equatable {
        let debts: [Debt]
        let goals: [Goal]
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DincrSpacing.s4) {
                if !model.flags.isEnabled(.financialWrites) {
                    StatusBanner(tone: .warning, title: tx("Cambios temporalmente pausados", "Changes temporarily paused"),
                                 message: model.flags.message(.financialWrites, language: model.language)
                                    ?? tx("Podés ver tu información; guardar cambios está en pausa por mantenimiento.", "You can see your information; saving changes is paused for maintenance."))
                }
                if let notice {
                    StatusBanner(tone: .info, title: notice, message: "")
                        .accessibilityIdentifier("plan.notice")
                }
                switch state {
                case .loading:
                    SkeletonView(rows: 4)
                case .failed(let message):
                    ErrorStateView(message: message) { Task { await load() } }
                case .loaded(let snapshot):
                    debtsSection(snapshot.debts)
                    goalsSection(snapshot.goals)
                }
            }
            .padding(.horizontal, DincrSpacing.s4)
            .padding(.bottom, DincrSpacing.s6)
            .frame(maxWidth: 600)
            .frame(maxWidth: .infinity)
        }
        .dincrScreenBackground()
        .navigationTitle(tx("Plan", "Plan"))
        .refreshable { await load() }
        .task { if case .loading = state { await load() } }
        .sheet(item: $action) { action in
            AmountSheet(action: action) { message in
                notice = message
                Task { await load() }
            }
            .presentationDetents([.medium])
        }
    }

    private var canWrite: Bool { model.flags.isEnabled(.financialWrites) }

    @ViewBuilder
    private func debtsSection(_ debts: [Debt]) -> some View {
        Text(tx("Deudas", "Debts")).font(DincrFont.title2).foregroundStyle(DincrColor.text).accessibilityAddTraits(.isHeader)
        if debts.isEmpty {
            Text(tx("No tenés deudas registradas.", "You have no debts recorded.")).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
        }
        ForEach(debts) { debt in
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                HStack {
                    Text(debt.name ?? tx("Deuda", "Debt")).font(DincrFont.body.weight(.semibold))
                    Spacer()
                    MoneyText(debt.remainingAmount)
                }
                .accessibilityElement(children: .combine)
                if let percent = debt.progressPercent {
                    DincrProgressBar(fraction: percent / 100)
                    Text(tx("\(Int(percent.rounded()))% pagado", "\(Int(percent.rounded()))% paid")).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                }
                if canWrite, (debt.remainingAmount ?? 0) > 0 {
                    Button(tx("Registrar pago", "Record payment")) { action = .payDebt(debt) }
                        .buttonStyle(.dincrSecondary)
                        .accessibilityIdentifier("debt.pay.\(debt.id)")
                }
            }
            .dincrCard()
        }
    }

    @ViewBuilder
    private func goalsSection(_ goals: [Goal]) -> some View {
        Text(tx("Metas", "Goals")).font(DincrFont.title2).foregroundStyle(DincrColor.text).accessibilityAddTraits(.isHeader).padding(.top, DincrSpacing.s2)
        if goals.isEmpty {
            Text(tx("Todavía no tenés metas.", "You have no goals yet.")).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
        }
        ForEach(goals) { goal in
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                HStack {
                    Text(goal.name ?? tx("Meta", "Goal")).font(DincrFont.body.weight(.semibold))
                    Spacer()
                    MoneyText(goal.currentAmount)
                }
                .accessibilityElement(children: .combine)
                if let target = goal.targetAmount, target > 0 {
                    let fraction = NSDecimalNumber(decimal: (goal.currentAmount ?? 0) / target).doubleValue
                    DincrProgressBar(fraction: fraction)
                    HStack(spacing: 4) {
                        Text(tx("Meta:", "Target:")).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                        MoneyText(target, font: DincrFont.caption)
                    }
                }
                if canWrite, goal.status != "completed", goal.remaining.map({ $0 > 0 }) ?? true {
                    Button(tx("Aportar", "Contribute")) { action = .contribute(goal) }
                        .buttonStyle(.dincrSecondary)
                        .accessibilityIdentifier("goal.contribute.\(goal.id)")
                }
            }
            .dincrCard()
        }
    }

    private func load() async {
        let epoch = model.currentEpoch
        let service = model.service
        do {
            async let debts = service.debts()
            async let goals = service.goals()
            state = .loaded(Snapshot(debts: try await debts, goals: try await goals))
        } catch is CancellationError {
            return
        } catch {
            if let message = model.message(for: error, epoch: epoch, fallback: tx("No pudimos cargar tu plan.", "We couldn’t load your plan.")) {
                state = .failed(message)
            }
        }
    }
}

enum AmountAction: Identifiable {
    case payDebt(Debt)
    case contribute(Goal)

    var id: String {
        switch self {
        case .payDebt(let debt): "debt-\(debt.id)"
        case .contribute(let goal): "goal-\(goal.id)"
        }
    }
}

/// One amount, typed in the user's own separators, sent once per submission.
struct AmountSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let action: AmountAction
    let onDone: (String) -> Void
    @State private var text = ""
    @State private var error: String?
    @State private var saving = false
    /// The key of the last submission; a retry of the same amount reuses it (no double payment).
    @State private var submission: (amount: Decimal, key: String)?

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
        .interactiveDismissDisabled(saving)
    }

    private var title: String {
        switch action {
        case .payDebt: tx("Registrar pago", "Record payment")
        case .contribute(let goal): tx("Aportar a «\(goal.name ?? "")»", "Contribute to “\(goal.name ?? "")”")
        }
    }

    private var confirm: String {
        switch action {
        case .payDebt: tx("Registrar", "Record")
        case .contribute: tx("Aportar", "Contribute")
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
        }
    }

    private func submit() async {
        guard !saving else { return }
        guard let amount = AmountInput.parse(text, separators: model.moneyFormat.separators) else {
            let example = model.moneyFormat.inputText(Decimal(string: "18450.5")!)
            error = tx("Escribí un monto mayor que cero, por ejemplo \(example).", "Enter an amount above zero, for example \(example).")
            return
        }
        let key = (submission?.amount == amount ? submission?.key : nil) ?? UUID().uuidString.lowercased()
        submission = (amount, key)
        saving = true; error = nil
        defer { saving = false }
        let epoch = model.currentEpoch
        do {
            switch action {
            case .payDebt(let debt):
                _ = try await model.service.payDebt(id: debt.id, amount: amount, idempotencyKey: key)
                onDone(tx("Pago registrado", "Payment recorded"))
            case .contribute(let goal):
                _ = try await model.service.contribute(goalID: goal.id, GoalContribution(amount: amount, contributionDate: Self.today()), idempotencyKey: key)
                onDone(tx("Aporte registrado", "Contribution recorded"))
            }
            dismiss()
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardar. Intentá de nuevo.", "We couldn’t save. Please try again."))
        }
    }

    static func today() -> String {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter.string(from: .now)
    }
}
