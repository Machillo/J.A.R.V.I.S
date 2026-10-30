import DincrCore
import DincrDesign
import SwiftUI

/// FX-1 — Plan → Gastos fijos (VIP and the Owner): what is paid every month, to see, add, edit and
/// remove. VIP: its recurring expenses (the obligations its Salvavidas reads). The Owner: his
/// `fixed_expenses` (the ones his Salvavidas and strategy read), through the Owner-only
/// `/finance/fixed-expenses`. Removing deactivates the row. Android twin: `FixedExpenses.kt`.
struct FixedExpensesView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        if Jarvis.isAvailable(to: model.profile) {
            OwnerFixedExpensesView()
        } else {
            RecurringView(expensesOnly: true)
        }
    }
}

private struct OwnerFixedExpensesView: View {
    @Environment(AppModel.self) private var model
    @State private var state: LoadState<[OwnerFixedExpense]> = .loading
    @State private var generation = 0
    @State private var creating = false
    @State private var editing: OwnerFixedExpense?
    @State private var removing: OwnerFixedExpense?
    @State private var notice: String?

    private var canWrite: Bool { model.flags.isEnabled(.financialWrites) }

    var body: some View {
        ScreenScroll(title: tx("Gastos fijos", "Fixed expenses")) {
            WritesPausedBanner()
            if let notice { StatusBanner(tone: .info, title: notice, message: "").accessibilityIdentifier("fixedExpenses.notice") }
            switch state {
            case .loading:
                SkeletonView(rows: 4)
            case .failed(let message):
                ErrorStateView(message: message) { generation += 1 }
            case .loaded(let items):
                if items.isEmpty {
                    EmptyStateView(symbol: "list.bullet.rectangle", title: tx("Todavía no hay gastos fijos", "No fixed expenses yet"),
                                   message: tx("Agregá lo que pagás todos los meses.", "Add what you pay every month.")) { EmptyView() }
                        .accessibilityIdentifier("fixedExpenses.empty")
                } else {
                    VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                        FigureRow(label: tx("Total por mes", "Total per month"), amount: items.compactMap(\.monthlyAmount).reduce(0, +))
                            .accessibilityIdentifier("fixedExpenses.total")
                    }
                    .dincrCard()
                    ForEach(items) { item in
                        OwnerFixedExpenseRow(item: item, canWrite: canWrite, edit: { editing = item }, remove: { removing = item })
                    }
                }
            }
        }
        .toolbar {
            if canWrite {
                Button { creating = true } label: { Label(tx("Agregar", "Add"), systemImage: "plus") }
                    .accessibilityIdentifier("fixedExpenses.add")
            }
        }
        .task(id: generation) { await load() }
        .sheet(isPresented: $creating) { OwnerFixedExpenseForm(editing: nil) { done($0) } }
        .sheet(item: $editing) { item in OwnerFixedExpenseForm(editing: item) { done($0) } }
        .confirmationDialog(tx("¿Quitar «\(removing?.name ?? "")»?", "Remove “\(removing?.name ?? "")”?"),
                            isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } }), titleVisibility: .visible) {
            Button(tx("Quitar", "Remove"), role: .destructive) { if let item = removing { Task { await remove(item) } } }
                .accessibilityIdentifier("fixedExpenses.confirmRemove")
            Button(tx("Cancelar", "Cancel"), role: .cancel) {}
        } message: {
            Text(tx("Deja de contarse en tu Salvavidas y tu plan.", "It stops counting in your emergency fund and your plan."))
        }
    }

    private func done(_ message: String) {
        notice = message
        generation += 1
    }

    private func load() async {
        let epoch = model.currentEpoch
        do {
            let items = try await model.service.ownerFixedExpenses()
            if epoch == model.currentEpoch { state = .loaded(items) }
        } catch is CancellationError {
            return
        } catch {
            if let message = model.message(for: error, epoch: epoch, fallback: tx("No pudimos cargar tus gastos fijos.", "We couldn’t load your fixed expenses.")) {
                state = .failed(message)
            }
        }
    }

    private func remove(_ item: OwnerFixedExpense) async {
        let epoch = model.currentEpoch
        do {
            try await model.service.removeOwnerFixedExpense(id: item.id)
            done(tx("Gasto fijo quitado", "Fixed expense removed"))
        } catch {
            notice = model.message(for: error, epoch: epoch, fallback: tx("No pudimos quitarlo.", "We couldn’t remove it."))
        }
    }
}

private struct OwnerFixedExpenseRow: View {
    let item: OwnerFixedExpense
    let canWrite: Bool
    let edit: () -> Void
    let remove: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(item.name ?? tx("Gasto", "Expense")).font(DincrFont.body.weight(.semibold))
                    Text([OwnerFixedExpense.intervalLabel(item.intervalMonths), item.dueDay.map { tx("día \($0)", "day \($0)") }, item.category]
                        .compactMap { $0 }.joined(separator: " · "))
                        .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                }
                Spacer()
                MoneyText(item.expectedAmount, currency: item.currency)
            }
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("fixedExpenses.row.\(item.id)")
            if canWrite {
                HStack {
                    Button(tx("Editar", "Edit"), action: edit).buttonStyle(.dincrSecondary)
                        .accessibilityIdentifier("fixedExpenses.edit.\(item.id)")
                    Button(tx("Quitar", "Remove"), role: .destructive, action: remove).frame(minHeight: 44)
                        .accessibilityIdentifier("fixedExpenses.remove.\(item.id)")
                }
            }
        }
        .dincrCard()
    }
}

/// Adds a fixed expense, or edits one (name, amount, category, every how many months, day).
private struct OwnerFixedExpenseForm: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let editing: OwnerFixedExpense?
    let onDone: (String) -> Void
    @State private var name = ""
    @State private var amount = ""
    @State private var category = "Gastos fijos"
    @State private var interval = 1
    @State private var day = ""
    @State private var error: String?
    @State private var saving = false
    @State private var loaded = false

    var body: some View {
        NavigationStack {
            Form {
                TextField(tx("Nombre", "Name"), text: $name).accessibilityIdentifier("fixedExpenses.name")
                MoneyField(label: tx("Monto", "Amount"), text: $amount, identifier: "fixedExpenses.amount")
                TextField(tx("Categoría", "Category"), text: $category)
                Picker(tx("Se paga", "Paid"), selection: $interval) {
                    ForEach(OwnerFixedExpenseRequest.intervals, id: \.self) { Text(OwnerFixedExpense.intervalLabel($0)).tag($0) }
                }
                TextField(tx("Día de pago (1–31, opcional)", "Payment day (1–31, optional)"), text: $day).keyboardType(.numberPad)
                    .accessibilityIdentifier("fixedExpenses.day")
                if let error { Text(error).foregroundStyle(DincrColor.negative).accessibilityIdentifier("fixedExpenses.error") }
            }
            .navigationTitle(editing == nil ? tx("Nuevo gasto fijo", "New fixed expense") : tx("Editar gasto fijo", "Edit fixed expense"))
            .navigationBarTitleDisplayMode(.inline)
            .onAppear(perform: prefill)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(tx("Cancelar", "Cancel")) { dismiss() }.disabled(saving) }
                ToolbarItem(placement: .confirmationAction) {
                    Button(tx("Guardar", "Save")) { Task { await save() } }.disabled(saving).accessibilityIdentifier("fixedExpenses.save")
                }
            }
        }
    }

    private func prefill() {
        guard let editing, !loaded else { return }
        loaded = true
        name = editing.name ?? ""
        amount = editing.expectedAmount.map(model.moneyFormat.inputText) ?? ""
        category = editing.category ?? "Gastos fijos"
        interval = OwnerFixedExpenseRequest.intervals.contains(editing.intervalMonths ?? 1) ? editing.intervalMonths ?? 1 : 1
        day = editing.dueDay.map(String.init) ?? ""
    }

    private func save() async {
        let value = CorrectionInput.amount(amount, separators: model.moneyFormat.separators)
        let dueDay = day.trimmingCharacters(in: .whitespaces).isEmpty ? nil : (Int(day) ?? 0)
        if let problem = OwnerFixedExpenseRequest.problem(name: name, amount: value, intervalMonths: interval, dueDay: dueDay) {
            error = problem; return
        }
        guard let value else { return }
        let trimmedCategory = category.trimmingCharacters(in: .whitespaces)
        let request = OwnerFixedExpenseRequest(name: name.trimmingCharacters(in: .whitespaces), category: trimmedCategory.isEmpty ? "Gastos fijos" : trimmedCategory,
                                               expectedAmount: value, intervalMonths: interval, dueDay: dueDay)
        saving = true; error = nil
        defer { saving = false }
        let epoch = model.currentEpoch
        do {
            if let editing {
                try await model.service.updateOwnerFixedExpense(id: editing.id, request)
                onDone(tx("Gasto fijo actualizado", "Fixed expense updated"))
            } else {
                try await model.service.createOwnerFixedExpense(request)
                onDone(tx("Gasto fijo agregado", "Fixed expense added"))
            }
            dismiss()
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardar.", "We couldn’t save."))
        }
    }
}
