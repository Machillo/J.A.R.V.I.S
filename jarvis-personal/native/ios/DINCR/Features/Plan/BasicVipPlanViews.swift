import DincrCore
import DincrDesign
import SwiftUI

/// PARITY E8 — guided budget (Basic): spent vs limit per category; editing replaces every limit.
struct BudgetView: View {
    @Environment(AppModel.self) private var model
    @State private var generation = 0
    @State private var editing: BudgetEdit?
    @State private var notice: String?

    var body: some View {
        ScreenScroll(title: tx("Presupuesto", "Budget")) {
            WritesPausedBanner()
            if let notice { StatusBanner(tone: .info, title: notice, message: "") }
            AsyncContent(load: { try await model.service.budget() }) { budget, _ in
                BudgetContent(budget: budget, canEdit: model.flags.isEnabled(.financialWrites)) { editing = BudgetEdit(budget: budget) }
            }
            .id(generation)
        }
        .sheet(item: $editing) { edit in
            BudgetEditor(budget: edit.budget) { message in notice = message; generation += 1 }
        }
    }
}

private struct BudgetEdit: Identifiable {
    let id = UUID()
    let budget: Budget
}

private struct BudgetContent: View {
    let budget: Budget
    let canEdit: Bool
    let edit: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            FigureRow(label: tx("Total presupuestado", "Total budgeted"), amount: budget.totalBudgeted)
            FigureRow(label: tx("Disponible para categorías", "Available for categories"), amount: budget.availableForCategories)
        }
        .dincrCard()
        let items = budget.items ?? []
        if items.isEmpty {
            EmptyStateView(symbol: "chart.pie", title: tx("Sin límites todavía", "No limits yet"),
                           message: tx("Definí cuánto querés gastar por categoría y DINCR te avisa cuando te acercás.", "Set how much you want to spend per category and DINCR tells you when you get close.")) { EmptyView() }
        }
        ForEach(items) { item in
            let limit = item.monthlyLimit ?? 0
            let spent = item.spent ?? 0
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                HStack {
                    Text(CategoryStyle.label(item.category)).font(DincrFont.body.weight(.semibold))
                    Spacer()
                    MoneyText(spent, font: DincrFont.bodySmall.monospacedDigit())
                    Text("/").foregroundStyle(DincrColor.textMuted)
                    MoneyText(limit, font: DincrFont.bodySmall.monospacedDigit())
                }
                .accessibilityElement(children: .combine)
                DincrProgressBar(fraction: limit > 0 ? NSDecimalNumber(decimal: spent / limit).doubleValue : 0, isOver: spent > limit && limit > 0)
                if spent > limit && limit > 0 {
                    Text(tx("Pasaste el límite", "Over the limit")).font(DincrFont.caption).foregroundStyle(DincrColor.negative)
                }
            }
            .dincrCard()
        }
        if canEdit {
            Button(tx("Editar límites", "Edit limits"), action: edit).buttonStyle(.dincrSecondary).accessibilityIdentifier("budget.edit")
        }
    }
}

private struct BudgetEditor: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let budget: Budget
    let onDone: (String) -> Void
    @State private var rows: [Row] = []
    @State private var newCategory = ""
    @State private var error: String?
    @State private var saving = false
    @State private var key = IdempotencyKey.new()

    struct Row: Identifiable, Equatable {
        let id = UUID()
        var category: String
        var limit: String
    }

    var body: some View {
        NavigationStack {
            Form {
                ForEach($rows) { $row in
                    VStack(alignment: .leading) {
                        Text(CategoryStyle.label(row.category)).font(DincrFont.label)
                        MoneyField(label: tx("Límite mensual", "Monthly limit"), text: $row.limit)
                    }
                }
                .onDelete { rows.remove(atOffsets: $0) }
                Section(tx("Agregar categoría", "Add a category")) {
                    HStack {
                        TextField(tx("Categoría", "Category"), text: $newCategory)
                        Button(tx("Agregar", "Add")) {
                            let name = newCategory.trimmingCharacters(in: .whitespaces)
                            guard !name.isEmpty, !rows.contains(where: { $0.category.lowercased() == name.lowercased() }) else { return }
                            rows.append(Row(category: name, limit: ""))
                            newCategory = ""
                        }
                    }
                }
                if let error { Text(error).foregroundStyle(DincrColor.negative) }
            }
            .navigationTitle(tx("Límites", "Limits"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(tx("Cancelar", "Cancel")) { dismiss() }.disabled(saving) }
                ToolbarItem(placement: .confirmationAction) { Button(tx("Guardar", "Save")) { Task { await save() } }.disabled(saving) }
            }
            .onAppear {
                if rows.isEmpty {
                    rows = (budget.items ?? []).map { Row(category: $0.category, limit: $0.monthlyLimit.map(model.moneyFormat.inputText) ?? "") }
                }
            }
        }
    }

    private func save() async {
        var limits: [BudgetUpdate.Limit] = []
        for row in rows {
            guard let amount = AmountInput.parseZeroOrMore(row.limit, separators: model.moneyFormat.separators) else {
                error = model.moneyFormat.amountHint; return
            }
            limits.append(BudgetUpdate.Limit(category: row.category, monthlyLimit: amount))
        }
        saving = true; error = nil
        defer { saving = false }
        let epoch = model.currentEpoch
        do {
            _ = try await model.service.updateBudget(BudgetUpdate(items: limits), idempotencyKey: key)
            onDone(tx("Presupuesto actualizado", "Budget updated"))
            dismiss()
        } catch {
            key = IdempotencyKey.new() // a full replacement: a new body is a new submission
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardar.", "We couldn’t save."))
        }
    }
}

/// PARITY E9 — the month's known payments and income (Basic).
struct CalendarView: View {
    @Environment(AppModel.self) private var model
    @State private var period = Period.current

    var body: some View {
        ScreenScroll(title: tx("Calendario", "Calendar")) {
            MonthPicker(period: $period)
            AsyncContent(load: { try await model.service.calendar(period: period) }) { calendar, _ in
                CalendarContent(calendar: calendar)
            }
            .id(period)
        }
    }
}

private struct CalendarContent: View {
    let calendar: FinancialCalendar

    var body: some View {
        if let summary = calendar.summary {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                FigureRow(label: tx("Pagos conocidos", "Known payments"), amount: summary.payments)
                InfoRow(label: tx("Compromisos", "Commitments"), value: "\(summary.commitments ?? 0)")
            }
            .dincrCard()
        }
        let events = calendar.events ?? []
        if events.isEmpty {
            EmptyStateView(symbol: "calendar", title: tx("Nada agendado", "Nothing scheduled"),
                           message: tx("Tus pagos recurrentes y cuotas aparecerán acá.", "Your recurring payments and installments will appear here.")) { EmptyView() }
        }
        ForEach(Array(events.enumerated()), id: \.offset) { _, event in
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(event.name ?? "").font(DincrFont.body.weight(.semibold))
                    Text(Day.label(event.date)).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                }
                Spacer()
                MoneyText(event.amount, sign: event.kind == "income" ? .income : .expense)
            }
            .accessibilityElement(children: .combine)
            .dincrCard(padding: DincrSpacing.s3)
        }
    }
}

/// PARITY E10 — recurring items (Basic): list, pause/activate, add, delete.
struct RecurringView: View {
    @Environment(AppModel.self) private var model
    @State private var generation = 0
    @State private var creating = false
    @State private var notice: String?
    @State private var deleting: RecurringList.Item?
    @State private var editing: RecurringList.Item?

    var body: some View {
        ScreenScroll(title: tx("Movimientos recurrentes", "Recurring transactions")) {
            WritesPausedBanner()
            if let notice { StatusBanner(tone: .info, title: notice, message: "") }
            AsyncContent(load: { try await model.service.recurring() }) { list, _ in
                RecurringContent(list: list, canWrite: model.flags.isEnabled(.financialWrites),
                                 toggle: { item in Task { await toggle(item) } }, edit: { item in editing = item }, delete: { item in deleting = item })
            }
            .id(generation)
        }
        .toolbar {
            if model.flags.isEnabled(.financialWrites) {
                Button { creating = true } label: { Label(tx("Agregar", "Add"), systemImage: "plus") }
            }
        }
        .sheet(isPresented: $creating) { RecurringForm { notice = $0; generation += 1 } }
        .sheet(item: $editing) { item in RecurringForm(editing: item) { notice = $0; generation += 1 } }
        .confirmationDialog(tx("¿Eliminar «\(deleting?.name ?? "")»?", "Delete “\(deleting?.name ?? "")”?"),
                            isPresented: Binding(get: { deleting != nil }, set: { if !$0 { deleting = nil } }), titleVisibility: .visible) {
            Button(tx("Eliminar", "Delete"), role: .destructive) { if let item = deleting { Task { await delete(item) } } }
            Button(tx("Cancelar", "Cancel"), role: .cancel) {}
        } message: {
            Text(tx("No se puede deshacer.", "This can’t be undone."))
        }
    }

    private func toggle(_ item: RecurringList.Item) async {
        guard let amount = item.amount else { return }
        // Only the editable fields are sent; the category keeps the backend's own default when unknown.
        let request = RecurringRequest(name: item.name ?? "", amount: amount, category: item.category ?? "general", itemType: item.itemType ?? "expense",
                                       frequency: item.frequency ?? "monthly", dueDay: item.dueDay, isActive: !(item.isActive ?? true))
        await run { _ = try await model.service.updateRecurring(id: item.id, request, idempotencyKey: IdempotencyKey.new()) }
    }

    private func delete(_ item: RecurringList.Item) async {
        await run { try await model.service.deleteRecurring(id: item.id) }
    }

    private func run(_ operation: () async throws -> Void) async {
        let epoch = model.currentEpoch
        do {
            try await operation()
            generation += 1
        } catch {
            notice = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardarlo.", "We couldn’t save it."))
        }
    }
}

private struct RecurringContent: View {
    let list: RecurringList
    let canWrite: Bool
    let toggle: (RecurringList.Item) -> Void
    let edit: (RecurringList.Item) -> Void
    let delete: (RecurringList.Item) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            FigureRow(label: tx("Gastos mensuales", "Monthly expenses"), amount: list.monthlyExpenses)
            FigureRow(label: tx("Gastos anuales", "Annual expenses"), amount: list.annualExpenses)
        }
        .dincrCard()
        ForEach(list.items ?? []) { item in
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(item.name ?? "").font(DincrFont.body.weight(.semibold))
                        Text([RecurringForm.label(item.frequency), item.dueDay.map { tx("día \($0)", "day \($0)") }].compactMap { $0 }.joined(separator: " · "))
                            .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                    }
                    Spacer()
                    MoneyText(item.amount, sign: item.itemType == "income" ? .income : .expense)
                }
                .accessibilityElement(children: .combine)
                if canWrite {
                    HStack {
                        Button((item.isActive ?? true) ? tx("Pausar", "Pause") : tx("Activar", "Activate")) { toggle(item) }.buttonStyle(.dincrSecondary)
                        Button(tx("Editar", "Edit")) { edit(item) }.frame(minHeight: 44)
                            .accessibilityIdentifier("recurring.edit")
                        Button(tx("Eliminar", "Delete"), role: .destructive) { delete(item) }.frame(minHeight: 44)
                            .accessibilityIdentifier("recurring.delete")
                    }
                }
            }
            .opacity((item.isActive ?? true) ? 1 : 0.6)
            .dincrCard()
        }
    }
}

/// Creates a recurring commitment, or edits one (`editing`: every field, its active state kept).
private struct RecurringForm: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    var editing: RecurringList.Item?
    let onDone: (String) -> Void
    @State private var name = ""
    @State private var amount = ""
    @State private var category = "Servicios"
    @State private var income = false
    @State private var frequency = "monthly"
    @State private var day = ""
    @State private var error: String?
    @State private var saving = false
    @State private var key = IdempotencyKey.new()
    @State private var loaded = false

    static func label(_ frequency: String?) -> String? {
        switch frequency {
        case "weekly": tx("Semanal", "Weekly")
        case "biweekly": tx("Quincenal", "Every two weeks")
        case "monthly": tx("Mensual", "Monthly")
        case "quarterly": tx("Trimestral", "Quarterly")
        case "annual": tx("Anual", "Yearly")
        default: nil
        }
    }

    var body: some View {
        NavigationStack {
            Form {
                Picker(tx("Tipo", "Type"), selection: $income) {
                    Text(tx("Gasto", "Expense")).tag(false)
                    Text(tx("Ingreso", "Income")).tag(true)
                }
                .pickerStyle(.segmented)
                TextField(tx("Nombre", "Name"), text: $name).accessibilityIdentifier("recurring.name")
                MoneyField(label: tx("Monto", "Amount"), text: $amount, identifier: "recurring.amount")
                TextField(tx("Categoría", "Category"), text: $category)
                Picker(tx("Frecuencia", "Frequency"), selection: $frequency) {
                    ForEach(RecurringRequest.frequencies, id: \.self) { Text(Self.label($0) ?? $0).tag($0) }
                }
                TextField(tx("Día (1–31, opcional)", "Day (1–31, optional)"), text: $day).keyboardType(.numberPad)
                if let error { Text(error).foregroundStyle(DincrColor.negative) }
            }
            .navigationTitle(editing == nil ? tx("Nuevo recurrente", "New recurring item") : tx("Editar recurrente", "Edit recurring item"))
            .onAppear(perform: prefill)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(tx("Cancelar", "Cancel")) { dismiss() }.disabled(saving) }
                ToolbarItem(placement: .confirmationAction) { Button(tx("Guardar", "Save")) { Task { await save() } }.disabled(saving) }
            }
        }
    }

    private func prefill() {
        guard let editing, !loaded else { return }
        loaded = true
        name = editing.name ?? ""
        amount = editing.amount.map(model.moneyFormat.inputText) ?? ""
        category = editing.category ?? "general"
        income = editing.itemType == "income"
        frequency = editing.frequency ?? "monthly"
        day = editing.dueDay.map(String.init) ?? ""
    }

    private func save() async {
        let trimmed = name.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { error = tx("Escribí un nombre.", "Enter a name."); return }
        guard let value = AmountInput.parse(amount, separators: model.moneyFormat.separators) else { error = model.moneyFormat.amountHint; return }
        let dueDay = day.isEmpty ? nil : Int(day)
        if !day.isEmpty && !(1...31).contains(dueDay ?? 0) { error = tx("El día va de 1 a 31.", "The day goes from 1 to 31."); return }
        let request = RecurringRequest(name: trimmed, amount: value, category: category.isEmpty ? "general" : category, itemType: income ? "income" : "expense",
                                       frequency: frequency, dueDay: dueDay, isActive: editing?.isActive ?? true)
        saving = true; error = nil
        defer { saving = false }
        let epoch = model.currentEpoch
        do {
            if let editing {
                _ = try await model.service.updateRecurring(id: editing.id, request, idempotencyKey: key)
                onDone(tx("Recurrente actualizado", "Recurring item updated"))
            } else {
                _ = try await model.service.createRecurring(request, idempotencyKey: key)
                onDone(tx("Recurrente agregado", "Recurring item added"))
            }
            dismiss()
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardar.", "We couldn’t save."))
        }
    }
}

/// PARITY E12 — aguinaldo estimate (VIP; paused with `vip_intelligence`; a 409 means no mailbox
/// is connected yet). "Sincronizar y recalcular" reads the mailbox again (`POST /vip/gmail/sync`)
/// and reloads; it is offered only while `gmail_automation` is on. Same flow as Android.
struct AguinaldoView: View {
    @Environment(AppModel.self) private var model
    @State private var generation = 0
    @State private var syncing = false
    @State private var error: String?

    var body: some View {
        ScreenScroll(title: tx("Aguinaldo", "Aguinaldo")) {
            if let error { ErrorStateView(message: error) }
            AsyncContent(load: { () async throws -> Aguinaldo? in
                // 409: not applicable yet (no connected mailbox); shown as an empty state, not an error.
                do { return try await model.service.aguinaldo() } catch let error as APIError where error.status == 409 { return nil }
            }) { aguinaldo, _ in
                AguinaldoContent(aguinaldo: aguinaldo)
            }
            .id(generation)
            if model.flags.isEnabled(.gmailAutomation) {
                Button(tx("Sincronizar y recalcular", "Sync and recalculate")) { Task { await syncAndReload() } }
                    .buttonStyle(.dincrPrimary(loading: syncing))
                    .disabled(syncing)
                    .accessibilityIdentifier("aguinaldo.sync")
            }
            Text(tx("Estimación según la ley costarricense; confirmala con tu patrono.", "Estimate under Costa Rican law; confirm it with your employer."))
                .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            FinancialDisclaimer()
        }
    }

    private func syncAndReload() async {
        guard !syncing else { return }
        syncing = true; error = nil
        defer { syncing = false }
        let epoch = model.currentEpoch
        do {
            _ = try await model.service.syncMail()
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos sincronizar tu correo.", "We couldn’t sync your mail."))
        }
        // Reload either way: the estimate is always the backend's latest answer.
        if epoch == model.currentEpoch { generation += 1 }
    }
}

private struct AguinaldoContent: View {
    let aguinaldo: Aguinaldo?

    var body: some View {
        if let aguinaldo {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                Text(tx("Aguinaldo acumulado", "Accrued aguinaldo")).font(DincrFont.label).foregroundStyle(DincrColor.text2)
                MoneyText(aguinaldo.accruedAguinaldo, currency: "CRC", font: DincrFont.displayAmount)
                FigureRow(label: tx("Salarios del periodo", "Salaries in the period"), amount: aguinaldo.earnedSalaryTotal, currency: "CRC")
                if let period = aguinaldo.period {
                    InfoRow(label: tx("Periodo", "Period"), value: "\(Day.label(period.start)) – \(Day.label(period.end))")
                }
                if let missing = aguinaldo.missingMonths, !missing.isEmpty {
                    Text(tx("Faltan salarios de \(missing.count) meses: el estimado puede ser menor al real.", "Salaries are missing for \(missing.count) months: the estimate may be lower than the real one."))
                        .font(DincrFont.caption).foregroundStyle(DincrColor.warning)
                }
            }
            .dincrCard()
        } else {
            EmptyStateView(symbol: "gift", title: tx("Todavía no podemos estimarlo", "We can’t estimate it yet"),
                           message: tx("Conectá tu correo en el Monitor de correo para detectar tus salarios.", "Connect your mail in the Email Monitor to detect your salaries.")) {
                NavigationLink(tx("Abrir Monitor de correo", "Open Email Monitor")) { EmailMonitorView() }.buttonStyle(.dincrPrimary)
            }
        }
    }
}
