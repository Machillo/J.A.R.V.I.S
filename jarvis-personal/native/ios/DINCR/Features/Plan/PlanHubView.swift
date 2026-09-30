import DincrCore
import DincrDesign
import SwiftUI

/// PARITY E1 — the Plan hub. Budget, calendar and recurring items are Basic; the emergency fund
/// and the aguinaldo are VIP (the aguinaldo also needs `gmail_automation`, as in Capacitor).
struct PlanHubView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ScreenScroll(title: tx("Plan", "Plan")) {
            WritesPausedBanner()
            VStack(spacing: DincrSpacing.s2) {
                link(DebtsView(), "creditcard", tx("Deudas", "Debts"), tx("Saldos, pagos y avance", "Balances, payments and progress"), id: "plan.debts")
                link(GoalsView(), "target", tx("Metas y ahorro", "Goals and savings"), tx("Metas, aportes y planes de ahorro", "Goals, contributions and savings plans"), id: "plan.goals")
                gated(.basic) { link(BudgetView(), "chart.pie", tx("Presupuesto", "Budget"), tx("Límites por categoría", "Limits per category"), id: "plan.budget") }
                gated(.basic) { link(CalendarView(), "calendar", tx("Calendario", "Calendar"), tx("Pagos y compromisos del mes", "Payments and commitments this month"), id: "plan.calendar") }
                gated(.basic) { link(RecurringView(), "repeat", tx("Recurrentes", "Recurring"), tx("Pagos e ingresos que se repiten", "Payments and income that repeat"), id: "plan.recurring") }
                if model.planTier == .vip && model.flags.isEnabled(.vipIntelligence) {
                    link(EmergencyFundView(), "lifepreserver", tx("Fondo de emergencia", "Emergency fund"), tx("Cuántos meses te cubre", "How many months it covers"), id: "plan.emergency")
                }
                if model.planTier == .vip && model.flags.isEnabled(.gmailAutomation) {
                    link(AguinaldoView(), "gift", tx("Aguinaldo", "Aguinaldo"), tx("Estimado según tus salarios", "Estimated from your salaries"), id: "plan.aguinaldo")
                }
            }
        }
    }

    @ViewBuilder
    private func gated<Row: View>(_ tier: PlanTier, @ViewBuilder _ row: () -> Row) -> some View {
        if model.planTier.rank >= tier.rank { row() }
    }

    private func link<Destination: View>(_ destination: Destination, _ symbol: String, _ title: String, _ subtitle: String, id: String) -> some View {
        NavigationLink { destination } label: { HubRow(symbol: symbol, title: title, subtitle: subtitle) }
            .buttonStyle(.plain)
            .dincrCard(padding: DincrSpacing.s3)
            .accessibilityIdentifier(id)
    }
}

/// B5 — writes paused by the operational switch: shown where money can be written.
struct WritesPausedBanner: View {
    @Environment(AppModel.self) private var model
    var body: some View {
        if !model.flags.isEnabled(.financialWrites) {
            StatusBanner(tone: .warning, title: tx("Cambios temporalmente pausados", "Changes temporarily paused"),
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
