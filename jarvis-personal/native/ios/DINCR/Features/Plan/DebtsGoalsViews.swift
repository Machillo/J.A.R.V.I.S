import DincrCore
import DincrDesign
import SwiftUI

// PARITY E2–E7 — debts, goals and savings plans. Balances are the backend's; the app sends what
// the user typed (validated before sending) and reloads the server's answer.

enum DebtStyle {
    static let types = ["credit_card", "loan", "other"]
    static func label(_ type: String?) -> String {
        switch type {
        case "credit_card": tx("Tarjeta de crédito", "Credit card")
        case "loan": tx("Préstamo", "Loan")
        default: tx("Otra deuda", "Other debt")
        }
    }
}

struct DebtsView: View {
    @Environment(AppModel.self) private var model
    @State private var generation = 0
    @State private var action: AmountAction?
    @State private var form: DebtForm.Mode?
    @State private var deleting: Debt?
    @State private var history: Debt?
    @State private var notice: String?

    var body: some View {
        ScreenScroll(title: tx("Deudas", "Debts")) {
            WritesPausedBanner()
            if let notice { StatusBanner(tone: .info, title: notice, message: "").accessibilityIdentifier("plan.notice") }
            AsyncContent(load: { try await model.service.debts() }) { debts, _ in
                DebtList(debts: debts, canWrite: model.flags.isEnabled(.financialWrites), canEdit: model.planTier.rank >= PlanTier.basic.rank,
                         pay: { action = .payDebt($0) }, edit: { form = .edit($0) }, delete: { deleting = $0 }, history: { history = $0 })
            }
            .id(generation)
        }
        .toolbar {
            if model.flags.isEnabled(.financialWrites) {
                Button { form = .create } label: { Label(tx("Agregar deuda", "Add debt"), systemImage: "plus") }
                    .accessibilityIdentifier("debts.add")
            }
        }
        .sheet(item: $action) { action in AmountSheet(action: action) { done($0) } }
        .sheet(item: $form) { mode in DebtForm(mode: mode) { done($0) } }
        .sheet(item: $history) { debt in DebtPaymentsSheet(debt: debt) }
        .confirmationDialog(tx("¿Eliminar «\(deleting?.name ?? "")»?", "Delete “\(deleting?.name ?? "")”?"),
                            isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } }), titleVisibility: .visible) {
            Button(tx("Eliminar", "Delete"), role: .destructive) { if let debt = deleting { Task { await delete(debt) } } }
            Button(tx("Cancelar", "Cancel"), role: .cancel) {}
        } message: {
            Text(tx("Se borra la deuda y su historial de pagos en DINCR. No se puede deshacer.", "The debt and its payment history in DINCR are removed. This can’t be undone."))
        }
    }

    private func done(_ message: String) {
        notice = message
        generation += 1
    }

    private func delete(_ debt: Debt) async {
        let epoch = model.currentEpoch
        do {
            try await model.service.deleteDebt(id: debt.id)
            done(tx("Deuda eliminada", "Debt deleted"))
        } catch {
            notice = model.message(for: error, epoch: epoch, fallback: tx("No pudimos eliminarla.", "We couldn’t delete it."))
        }
    }
}

private struct DebtList: View {
    let debts: [Debt]
    let canWrite: Bool
    let canEdit: Bool
    let pay: (Debt) -> Void
    let edit: (Debt) -> Void
    let delete: (Debt) -> Void
    let history: (Debt) -> Void

    var body: some View {
        if debts.isEmpty {
            EmptyStateView(symbol: "creditcard", title: tx("No tenés deudas registradas", "You have no debts recorded"),
                           message: tx("Agregá tarjetas o préstamos para ver tu avance y tu estrategia.", "Add cards or loans to see your progress and your strategy.")) { EmptyView() }
        }
        ForEach(debts) { debt in
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(debt.name ?? tx("Deuda", "Debt")).font(DincrFont.body.weight(.semibold))
                        Text(DebtStyle.label(debt.debtType)).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                    }
                    Spacer()
                    MoneyText(debt.remainingAmount)
                }
                .accessibilityElement(children: .combine)
                // The backend sends 0 % when the original amount is unknown: progress only from a known one.
                if let percent = debt.knownProgressPercent {
                    DincrProgressBar(fraction: percent / 100)
                    Text(tx("\(Int(percent.rounded()))% pagado", "\(Int(percent.rounded()))% paid")).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                }
                if let monthly = debt.monthlyPayment { FigureRow(label: tx("Cuota mensual", "Monthly payment"), amount: monthly) }
                if let next = debt.nextPaymentDate { InfoRow(label: tx("Próximo pago", "Next payment"), value: Day.label(next)) }
                // DEB-07a: the payments recorded for this debt (read-only, every plan).
                Button(tx("Ver pagos", "See payments")) { history(debt) }
                    .font(DincrFont.bodySmall.weight(.semibold)).foregroundStyle(DincrColor.tint)
                    .frame(minHeight: 44)
                    .accessibilityIdentifier("debt.history.\(debt.id)")
                if canWrite {
                    HStack(spacing: DincrSpacing.s2) {
                        if (debt.remainingAmount ?? 0) > 0 {
                            Button(tx("Registrar pago", "Record payment")) { pay(debt) }
                                .buttonStyle(.dincrSecondary)
                                .accessibilityIdentifier("debt.pay.\(debt.id)")
                        }
                        Menu {
                            if canEdit { Button(tx("Editar", "Edit"), systemImage: "pencil") { edit(debt) } }
                            Button(tx("Eliminar", "Delete"), systemImage: "trash", role: .destructive) { delete(debt) }
                        } label: {
                            Image(systemName: "ellipsis.circle").font(.title3).frame(minWidth: 44, minHeight: 44)
                        }
                        .accessibilityLabel(tx("Más acciones", "More actions"))
                    }
                }
            }
            .dincrCard()
        }
    }
}

/// DEB-07a — the payments recorded in DINCR for one debt, newest first (Android: the debt's
/// payments dialog). Only payments made with "Registrar pago" are linked to the debt.
private struct DebtPaymentsSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let debt: Debt

    var body: some View {
        NavigationStack {
            ScreenScroll(title: tx("Pagos registrados", "Recorded payments")) {
                Text(debt.name ?? tx("Deuda", "Debt")).font(DincrFont.title2).foregroundStyle(DincrColor.text)
                AsyncContent(load: { try await model.service.debtPayments(id: debt.id) }) { payments, _ in
                    if payments.isEmpty {
                        Text(tx("Todavía no registraste pagos de esta deuda en DINCR.", "You haven’t recorded payments for this debt in DINCR yet."))
                            .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                            .accessibilityIdentifier("debt.payments.empty")
                    } else {
                        VStack(spacing: 0) {
                            ForEach(payments) { payment in
                                HStack {
                                    Text(payment.paymentDate.map(Day.label) ?? "—").font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                                    Spacer()
                                    MoneyText(payment.amount, font: DincrFont.amount)
                                }
                                .frame(minHeight: 44)
                                .accessibilityElement(children: .combine)
                            }
                        }
                        .dincrCard()
                        .accessibilityElement(children: .contain)
                        .accessibilityIdentifier("debt.payments.list")
                    }
                }
                Text(tx("Aparecen los pagos registrados con «Registrar pago».", "Payments recorded with “Record payment” appear here."))
                    .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            }
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button(tx("Cerrar", "Close")) { dismiss() } } }
        }
    }
}

/// E3 — create (Free) or edit (Basic) a debt.
struct DebtForm: View {
    enum Mode: Identifiable {
        case create
        case edit(Debt)
        var id: String { if case .edit(let debt) = self { "d\(debt.id)" } else { "new" } }
    }

    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let mode: Mode
    let onDone: (String) -> Void
    @State private var name = ""
    @State private var type = "credit_card"
    @State private var remaining = ""
    @State private var total = ""
    @State private var monthly = ""
    @State private var rate = ""
    @State private var initialRate = ""
    @State private var day = ""
    @State private var error: String?
    @State private var saving = false
    /// One key per form: a retry after a lost response is answered from the first request; a
    /// changed body with the same key is refused (409) instead of creating a second record.
    @State private var key = IdempotencyKey.new()

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField(tx("Nombre", "Name"), text: $name).accessibilityIdentifier("debt.name")
                    Picker(tx("Tipo", "Type"), selection: $type) {
                        ForEach(DebtStyle.types, id: \.self) { Text(DebtStyle.label($0)).tag($0) }
                    }
                }
                Section {
                    MoneyField(label: tx("Saldo pendiente", "Outstanding balance"), text: $remaining, identifier: "debt.remaining")
                    MoneyField(label: tx("Monto original (opcional)", "Original amount (optional)"), text: $total)
                    MoneyField(label: tx("Cuota mensual (opcional)", "Monthly payment (optional)"), text: $monthly)
                }
                if model.planTier.rank >= PlanTier.basic.rank {
                    Section(tx("Detalles", "Details")) {
                        TextField(tx("Interés anual % (opcional)", "Annual interest % (optional)"), text: $rate).keyboardType(.decimalPad)
                        TextField(tx("Día de pago (1–31, opcional)", "Payment day (1–31, optional)"), text: $day).keyboardType(.numberPad)
                    }
                }
                if let error { Section { Text(error).foregroundStyle(DincrColor.negative) } }
            }
            .navigationTitle(isEditing ? tx("Editar deuda", "Edit debt") : tx("Nueva deuda", "New debt"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(tx("Cancelar", "Cancel")) { dismiss() }.disabled(saving) }
                ToolbarItem(placement: .confirmationAction) {
                    Button(tx("Guardar", "Save")) { Task { await save() } }.disabled(saving).accessibilityIdentifier("debt.save")
                }
            }
            .onAppear(perform: prefill)
        }
        .interactiveDismissDisabled(saving)
    }

    private var isEditing: Bool { if case .edit = mode { true } else { false } }

    private func prefill() {
        guard case .edit(let debt) = mode, name.isEmpty else { return }
        let format = model.moneyFormat
        name = debt.name ?? ""
        type = DebtStyle.types.contains(debt.debtType ?? "") ? debt.debtType! : "other"
        remaining = debt.remainingAmount.map(format.inputText) ?? ""
        total = debt.totalAmount.map(format.inputText) ?? ""
        monthly = debt.monthlyPayment.map(format.inputText) ?? ""
        // An unknown rate starts empty (never "0"), and the starting text is kept to tell whether
        // the user touched it.
        rate = debt.rateForEditing.map { "\($0)" } ?? ""
        initialRate = rate
        day = debt.paymentDay.map(String.init) ?? ""
    }

    private func save() async {
        let separators = model.moneyFormat.separators
        let trimmed = name.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { error = tx("Escribí un nombre.", "Enter a name."); return }
        guard let balance = AmountInput.parseZeroOrMore(remaining, separators: separators) else { error = model.moneyFormat.amountHint; return }
        let original = total.isEmpty ? nil : AmountInput.parse(total, separators: separators)
        let payment = monthly.isEmpty ? nil : AmountInput.parse(monthly, separators: separators)
        if (!total.isEmpty && original == nil) || (!monthly.isEmpty && payment == nil) { error = model.moneyFormat.amountHint; return }
        let interest = rate.isEmpty ? nil : Decimal(string: rate.replacingOccurrences(of: ",", with: "."), locale: Locale(identifier: "en_US_POSIX"))
        let paymentDay = day.isEmpty ? nil : Int(day)
        if (!rate.isEmpty && interest == nil) || (!day.isEmpty && !(1...31).contains(paymentDay ?? 0)) {
            error = tx("Revisá el interés y el día de pago.", "Check the interest and the payment day."); return
        }
        let request = DebtRequest(name: trimmed, debtType: type, remainingAmount: balance, totalAmount: original, monthlyPayment: payment,
                                  interestRate: interest, paymentDay: paymentDay,
                                  interestRateConfirmed: isEditing ? DebtRequest.rateConfirmed(initial: initialRate, current: rate) : nil)
        saving = true; error = nil
        defer { saving = false }
        let epoch = model.currentEpoch
        do {
            switch mode {
            case .create: _ = try await model.service.createDebt(request, idempotencyKey: key)
            case .edit(let debt): _ = try await model.service.updateDebt(id: debt.id, request, idempotencyKey: key)
            }
            onDone(isEditing ? tx("Deuda actualizada", "Debt updated") : tx("Deuda agregada", "Debt added"))
            dismiss()
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardar.", "We couldn’t save."))
        }
    }
}

struct GoalsView: View {
    @Environment(AppModel.self) private var model
    @State private var generation = 0
    @State private var action: AmountAction?
    @State private var goalForm: GoalForm.Mode?
    @State private var creatingPlan = false
    @State private var notice: String?
    @State private var confirming: PendingDelete?

    struct PendingDelete: Identifiable {
        let id = UUID()
        let name: String
        let run: () async throws -> Void
    }

    struct Snapshot: Equatable {
        let goals: [Goal]
        let plans: [SavingsPlan]
    }

    var body: some View {
        ScreenScroll(title: tx("Metas y ahorro", "Goals and savings")) {
            WritesPausedBanner()
            // UX-7: the declared available savings and emergency-fund target (moved from Situación).
            NavigationLink { DeclaredSavingsView() } label: {
                HubRow(symbol: "banknote", title: tx("Tus ahorros", "Your savings"),
                       subtitle: tx("Ahorros disponibles y meta de fondo de emergencia", "Available savings and emergency fund target"))
            }
            .buttonStyle(.plain)
            .dincrCard(padding: DincrSpacing.s3)
            .accessibilityIdentifier("goals.declaredSavings")
            if let notice { StatusBanner(tone: .info, title: notice, message: "").accessibilityIdentifier("plan.notice") }
            AsyncContent(load: { () async throws -> Snapshot in
                let service = model.service
                async let goals = service.goals()
                async let plans = service.savingsPlans()
                return Snapshot(goals: try await goals, plans: try await plans)
            }) { snapshot, _ in
                GoalsContent(snapshot: snapshot, canWrite: model.flags.isEnabled(.financialWrites), canEdit: model.planTier.rank >= PlanTier.basic.rank,
                             contribute: { action = .contribute($0) }, save: { action = .save($0) }, edit: { goalForm = .edit($0) },
                             deleteGoal: { goal in confirming = PendingDelete(name: goal.name ?? "") { try await model.service.deleteGoal(id: goal.id) } },
                             deletePlan: { plan in confirming = PendingDelete(name: plan.name ?? "") { try await model.service.deleteSavingsPlan(id: plan.id) } })
            }
            .id(generation)
        }
        .toolbar {
            if model.flags.isEnabled(.financialWrites) {
                Menu {
                    Button(tx("Nueva meta", "New goal"), systemImage: "target") { goalForm = .create }
                    Button(tx("Nuevo plan de ahorro", "New savings plan"), systemImage: "banknote") { creatingPlan = true }
                } label: { Label(tx("Agregar", "Add"), systemImage: "plus") }
                .accessibilityIdentifier("goals.add")
            }
        }
        .sheet(item: $action) { action in AmountSheet(action: action) { done($0) } }
        .sheet(item: $goalForm) { mode in GoalForm(mode: mode) { done($0) } }
        .sheet(isPresented: $creatingPlan) { SavingsPlanForm { done($0) } }
        .confirmationDialog(tx("¿Eliminar «\(confirming?.name ?? "")»?", "Delete “\(confirming?.name ?? "")”?"),
                            isPresented: Binding(get: { confirming != nil }, set: { if !$0 { confirming = nil } }), titleVisibility: .visible) {
            Button(tx("Eliminar", "Delete"), role: .destructive) {
                if let pending = confirming { Task { await delete(pending.run) } }
            }
            Button(tx("Cancelar", "Cancel"), role: .cancel) {}
        } message: {
            Text(tx("Se borra con su historial de aportes en DINCR. No se puede deshacer.", "It is removed with its contribution history in DINCR. This can’t be undone."))
        }
    }

    private func done(_ message: String) {
        notice = message
        generation += 1
    }

    private func delete(_ operation: () async throws -> Void) async {
        let epoch = model.currentEpoch
        do {
            try await operation()
            done(tx("Eliminado", "Deleted"))
        } catch {
            notice = model.message(for: error, epoch: epoch, fallback: tx("No pudimos eliminarlo.", "We couldn’t delete it."))
        }
    }
}

private struct GoalsContent: View {
    let snapshot: GoalsView.Snapshot
    let canWrite: Bool
    let canEdit: Bool
    let contribute: (Goal) -> Void
    let save: (SavingsPlan) -> Void
    let edit: (Goal) -> Void
    let deleteGoal: (Goal) -> Void
    let deletePlan: (SavingsPlan) -> Void

    var body: some View {
        SectionHeader(title: tx("Metas", "Goals"))
        if snapshot.goals.isEmpty {
            Text(tx("Todavía no tenés metas.", "You have no goals yet.")).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
        }
        ForEach(snapshot.goals) { goal in
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                HStack(alignment: .firstTextBaseline) {
                    Text(goal.name ?? tx("Meta", "Goal")).font(DincrFont.body.weight(.semibold))
                    Spacer()
                    MoneyText(goal.currentAmount)
                }
                .accessibilityElement(children: .combine)
                if let target = goal.targetAmount, target > 0 {
                    // Progress only from a known amount saved: an unknown one is not 0 % saved.
                    if let fraction = goal.progressFraction {
                        DincrProgressBar(fraction: fraction).accessibilityIdentifier("goal.progress.\(goal.id)")
                    }
                    FigureRow(label: tx("Meta", "Target"), amount: target)
                }
                if let date = goal.targetDate { InfoRow(label: tx("Fecha objetivo", "Target date"), value: Day.label(date)) }
                if canWrite {
                    HStack(spacing: DincrSpacing.s2) {
                        if goal.canContribute {
                            Button(tx("Aportar", "Contribute")) { contribute(goal) }
                                .buttonStyle(.dincrSecondary)
                                .accessibilityIdentifier("goal.contribute.\(goal.id)")
                        }
                        Menu {
                            if canEdit { Button(tx("Editar", "Edit"), systemImage: "pencil") { edit(goal) } }
                            Button(tx("Eliminar", "Delete"), systemImage: "trash", role: .destructive) { deleteGoal(goal) }
                        } label: { Image(systemName: "ellipsis.circle").font(.title3).frame(minWidth: 44, minHeight: 44) }
                        .accessibilityLabel(tx("Más acciones", "More actions"))
                    }
                }
            }
            .dincrCard()
        }
        SectionHeader(title: tx("Planes de ahorro", "Savings plans"))
        if snapshot.plans.isEmpty {
            Text(tx("Sin planes de ahorro.", "No savings plans.")).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
        }
        ForEach(snapshot.plans) { plan in
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                HStack(alignment: .firstTextBaseline) {
                    Text(plan.name ?? tx("Plan", "Plan")).font(DincrFont.body.weight(.semibold))
                    Spacer()
                    MoneyText(plan.savedAmount)
                }
                .accessibilityElement(children: .combine)
                FigureRow(label: tx("Aporte mensual", "Monthly amount"), amount: plan.monthlyAmount)
                if canWrite {
                    HStack {
                        Button(tx("Aportar", "Contribute")) { save(plan) }.buttonStyle(.dincrSecondary)
                        Button(tx("Eliminar", "Delete"), role: .destructive) { deletePlan(plan) }
                            .frame(minHeight: 44)
                    }
                }
            }
            .dincrCard()
        }
    }
}

/// E6 — create (Free) or edit (Basic) a goal.
struct GoalForm: View {
    enum Mode: Identifiable {
        case create
        case edit(Goal)
        var id: String { if case .edit(let goal) = self { "g\(goal.id)" } else { "new" } }
    }

    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let mode: Mode
    let onDone: (String) -> Void
    @State private var name = ""
    @State private var target = ""
    @State private var current = ""
    @State private var hasDate = false
    @State private var date = Date.now.addingTimeInterval(86_400 * 180)
    @State private var priority = "medium"
    @State private var error: String?
    @State private var saving = false
    /// One key per form: a retry after a lost response is answered from the first request; a
    /// changed body with the same key is refused (409) instead of creating a second record.
    @State private var key = IdempotencyKey.new()

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField(tx("Nombre", "Name"), text: $name).accessibilityIdentifier("goal.name")
                    MoneyField(label: tx("Meta", "Target"), text: $target, identifier: "goal.target")
                    MoneyField(label: tx("Ya ahorrado", "Already saved"), text: $current)
                }
                Section {
                    Picker(tx("Prioridad", "Priority"), selection: $priority) {
                        Text(tx("Alta", "High")).tag("high")
                        Text(tx("Media", "Medium")).tag("medium")
                        Text(tx("Baja", "Low")).tag("low")
                    }
                    Toggle(tx("Tiene fecha objetivo", "Has a target date"), isOn: $hasDate)
                    if hasDate { DatePicker(tx("Fecha", "Date"), selection: $date, in: Date.now..., displayedComponents: .date) }
                }
                if let error { Section { Text(error).foregroundStyle(DincrColor.negative) } }
            }
            .navigationTitle(isEditing ? tx("Editar meta", "Edit goal") : tx("Nueva meta", "New goal"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(tx("Cancelar", "Cancel")) { dismiss() }.disabled(saving) }
                ToolbarItem(placement: .confirmationAction) {
                    Button(tx("Guardar", "Save")) { Task { await save() } }.disabled(saving).accessibilityIdentifier("goal.save")
                }
            }
            .onAppear(perform: prefill)
        }
        .interactiveDismissDisabled(saving)
    }

    private var isEditing: Bool { if case .edit = mode { true } else { false } }

    private func prefill() {
        guard case .edit(let goal) = mode, name.isEmpty else { return }
        let format = model.moneyFormat
        name = goal.name ?? ""
        target = goal.targetAmount.map(format.inputText) ?? ""
        current = goal.currentAmount.map(format.inputText) ?? ""
        priority = GoalRequest.priorities.contains(goal.priority ?? "") ? goal.priority! : "medium"
        if let day = goal.targetDate, let parsed = MovementEditor.dayFormatter.date(from: String(day.prefix(10))) { hasDate = true; date = parsed }
    }

    private func save() async {
        let separators = model.moneyFormat.separators
        let trimmed = name.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { error = tx("Escribí un nombre.", "Enter a name."); return }
        guard let goalAmount = AmountInput.parse(target, separators: separators) else { error = model.moneyFormat.amountHint; return }
        let saved = current.isEmpty ? 0 : AmountInput.parseZeroOrMore(current, separators: separators)
        guard let saved else { error = model.moneyFormat.amountHint; return }
        var status: String?
        if case .edit(let goal) = mode { status = goal.status }
        let request = GoalRequest(name: trimmed, targetAmount: goalAmount, currentAmount: min(saved, goalAmount),
                                  targetDate: hasDate ? MovementEditor.dayFormatter.string(from: date) : nil, priority: priority, status: status)
        saving = true; error = nil
        defer { saving = false }
        let epoch = model.currentEpoch
        do {
            switch mode {
            case .create: _ = try await model.service.createGoal(request, idempotencyKey: key)
            case .edit(let goal): _ = try await model.service.updateGoal(id: goal.id, request, idempotencyKey: key)
            }
            onDone(isEditing ? tx("Meta actualizada", "Goal updated") : tx("Meta creada", "Goal created"))
            dismiss()
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardar.", "We couldn’t save."))
        }
    }
}

/// E7 — a new savings plan.
struct SavingsPlanForm: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let onDone: (String) -> Void
    @State private var name = ""
    @State private var monthly = ""
    @State private var start = Date.now
    @State private var end = Date.now.addingTimeInterval(86_400 * 365)
    @State private var error: String?
    @State private var saving = false
    /// One key per form: a retry after a lost response is answered from the first request; a
    /// changed body with the same key is refused (409) instead of creating a second record.
    @State private var key = IdempotencyKey.new()

    var body: some View {
        NavigationStack {
            Form {
                TextField(tx("Nombre", "Name"), text: $name)
                MoneyField(label: tx("Aporte mensual", "Monthly amount"), text: $monthly)
                DatePicker(tx("Inicio", "Start"), selection: $start, displayedComponents: .date)
                DatePicker(tx("Fin", "End"), selection: $end, in: start..., displayedComponents: .date)
                if let error { Text(error).foregroundStyle(DincrColor.negative) }
            }
            .navigationTitle(tx("Nuevo plan de ahorro", "New savings plan"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(tx("Cancelar", "Cancel")) { dismiss() }.disabled(saving) }
                ToolbarItem(placement: .confirmationAction) { Button(tx("Guardar", "Save")) { Task { await save() } }.disabled(saving) }
            }
        }
    }

    private func save() async {
        let trimmed = name.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { error = tx("Escribí un nombre.", "Enter a name."); return }
        guard let amount = AmountInput.parse(monthly, separators: model.moneyFormat.separators) else { error = model.moneyFormat.amountHint; return }
        let request = SavingsPlanRequest(name: trimmed, monthlyAmount: amount, savedAmount: 0,
                                         startDate: MovementEditor.dayFormatter.string(from: start), endDate: MovementEditor.dayFormatter.string(from: end))
        saving = true; error = nil
        defer { saving = false }
        let epoch = model.currentEpoch
        do {
            _ = try await model.service.createSavingsPlan(request, idempotencyKey: key)
            onDone(tx("Plan de ahorro creado", "Savings plan created"))
            dismiss()
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardar.", "We couldn’t save."))
        }
    }
}
