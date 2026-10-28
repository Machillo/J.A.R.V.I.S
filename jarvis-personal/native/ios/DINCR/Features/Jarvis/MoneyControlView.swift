import DincrCore
import DincrDesign
import SwiftUI

/// JARVIS → Control de dinero (Owner only): the historical "Cuentas por cobrar". Who owes the Owner
/// money in the current card cycle, how much, and each charge and payment; "Registrar pago" and
/// "Nuevo cobro" are explicit Owner commands. Opening the screen only reads. Every amount is the
/// backend's. Android: `MoneyControlScreen`.
struct MoneyControlView: View {
    @Environment(AppModel.self) private var model
    @State private var paying: Receivable?
    @State private var adding = false
    @State private var notice: String?
    @State private var reloadToken = 0

    var body: some View {
        ScreenScroll(title: tx("Control de dinero", "Money control")) {
            if let notice { StatusBanner(tone: .info, title: notice, message: "").accessibilityIdentifier("money.notice") }
            AsyncContent(fallback: tx("No pudimos cargar tus cobros.", "We couldn’t load your collections."),
                         load: { try await model.service.receivables() }) { report, _ in
                MoneyControlContent(report: report, pay: { paying = $0 })
            }
            .id(reloadToken)
            AdditionalCardsSection(reloadToken: reloadToken, onDone: done)
        }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { adding = true } label: { Image(systemName: "plus") }
                    .accessibilityLabel(tx("Nuevo cobro", "New collection"))
                    .accessibilityIdentifier("money.add")
            }
        }
        .sheet(item: $paying) { receivable in
            ReceivablePaymentSheet(receivable: receivable) { done($0) }
        }
        .sheet(isPresented: $adding) {
            ReceivableEntrySheet { done($0) }
        }
    }

    private func done(_ message: String) {
        notice = message
        reloadToken += 1
    }
}

private struct MoneyControlContent: View {
    let report: ReceivablesReport
    let pay: (Receivable) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Text(tx("Te deben", "Owed to you")).font(DincrFont.label).foregroundStyle(DincrColor.text2)
            MoneyText(report.summary?.totalPending, font: DincrFont.displayAmount)
            if let open = report.summary?.countOpen {
                Text(open == 1 ? tx("1 persona con saldo pendiente", "1 person with an amount due")
                               : tx("\(open) personas con saldo pendiente", "\(open) people with an amount due"))
                    .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            }
            if let start = report.cycle?.start, let end = report.cycle?.end {
                Text(tx("Ciclo de tarjeta: \(Day.label(start)) – \(Day.label(end))", "Card cycle: \(Day.label(start)) – \(Day.label(end))"))
                    .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            }
        }
        .dincrCard()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("money.summary")

        if report.items.isEmpty {
            EmptyStateView(symbol: "person.2", title: tx("Nadie te debe dinero", "No one owes you money"),
                           message: tx("Con «+» registrás lo que alguien te debe.", "Use “+” to record what someone owes you.")) { EmptyView() }
                .accessibilityIdentifier("money.empty")
        }
        ForEach(report.items) { receivable in
            ReceivableCard(receivable: receivable, pay: { pay(receivable) })
        }
    }
}

private struct ReceivableCard: View {
    let receivable: Receivable
    let pay: () -> Void
    @State private var showsHistory = false

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(receivable.personName ?? tx("Persona", "Person")).font(DincrFont.body.weight(.semibold))
                    Text(statusLabel + (receivable.isAuto ? tx(" · Tarjeta adicional", " · Additional card") : ""))
                        .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                }
                Spacer()
                MoneyText(receivable.currentAmountDue)
            }
            .accessibilityElement(children: .combine)
            if let carried = receivable.carriedPending, carried != 0 { FigureRow(label: tx("De ciclos anteriores", "From earlier cycles"), amount: carried) }
            if let charges = receivable.cycleCharges, charges > 0 { FigureRow(label: tx("Cargos de este ciclo", "Charges this cycle"), amount: charges) }
            if let payments = receivable.cyclePayments, payments > 0 { FigureRow(label: tx("Pagos de este ciclo", "Payments this cycle"), amount: payments) }
            HStack(spacing: DincrSpacing.s2) {
                if receivable.canRecordPayment {
                    Button(tx("Registrar pago", "Record payment"), action: pay)
                        .buttonStyle(.dincrSecondary)
                        .accessibilityIdentifier("money.pay.\(receivable.id)")
                }
                if !receivable.history.isEmpty {
                    Button(showsHistory ? tx("Ocultar movimientos", "Hide entries") : tx("Ver movimientos", "Show entries")) { showsHistory.toggle() }
                        .font(DincrFont.label).foregroundStyle(DincrColor.tint)
                        .accessibilityIdentifier("money.history.\(receivable.id)")
                }
            }
            if showsHistory {
                ForEach(receivable.history) { entry in
                    HStack(alignment: .firstTextBaseline) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(entry.isPayment ? tx("Pago", "Payment") : tx("Cargo", "Charge")).font(DincrFont.bodySmall)
                            Text([entry.entryDate.map { Day.label($0) }, entry.description].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "))
                                .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                        }
                        Spacer()
                        MoneyText(entry.amount.map { entry.isPayment ? -$0 : $0 })
                    }
                    .accessibilityElement(children: .combine)
                }
            }
        }
        .dincrCard()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("money.person.\(receivable.id)")
    }

    private var statusLabel: String {
        switch receivable.status {
        case .pending: tx("Pendiente", "Pending")
        case .partial: tx("Pagó una parte", "Partly paid")
        case .completed: tx("Al día", "Settled")
        case .credit: tx("Tiene saldo a favor", "Has credit")
        case .unknown: tx("Sin estado", "No status")
        }
    }
}

/// "Registrar pago": what the person paid. Saved once: the button is disabled while it is sent, and
/// it is never retried on its own (the backend does not deduplicate it).
private struct ReceivablePaymentSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let receivable: Receivable
    let onDone: (String) -> Void
    @State private var text = ""
    @State private var error: String?
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text(tx("Debe: \(model.moneyFormat.string(receivable.currentAmountDue ?? 0)).", "Owes: \(model.moneyFormat.string(receivable.currentAmountDue ?? 0))."))
                        .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                    TextField(tx("Monto", "Amount"), text: $text).keyboardType(.decimalPad).accessibilityIdentifier("money.payment.amount")
                    if let error { Text(error).font(DincrFont.caption).foregroundStyle(DincrColor.negative) }
                }
            }
            .navigationTitle(tx("Pago de \(receivable.personName ?? "")", "Payment from \(receivable.personName ?? "")"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(tx("Cancelar", "Cancel")) { dismiss() }.disabled(saving) }
                ToolbarItem(placement: .confirmationAction) {
                    Button(tx("Registrar", "Record")) { Task { await submit() } }.disabled(saving).accessibilityIdentifier("money.payment.save")
                }
            }
        }
        .presentationDetents([.medium])
        .interactiveDismissDisabled(saving)
    }

    private func submit() async {
        guard !saving else { return }
        guard let amount = AmountInput.parse(text, separators: model.moneyFormat.separators) else {
            error = model.moneyFormat.amountHint
            return
        }
        saving = true; error = nil
        defer { saving = false }
        let epoch = model.currentEpoch
        do {
            try await model.service.recordReceivablePayment(id: receivable.id, ReceivablePaymentRequest(amount: amount, paymentDate: Day.today()))
            onDone(tx("Pago registrado", "Payment recorded"))
            dismiss()
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos registrarlo. Revisá la lista antes de intentar de nuevo.", "We couldn’t record it. Check the list before trying again."))
        }
    }
}

/// "Nuevo cobro": money someone now owes the Owner. Saved once, like the payment.
private struct ReceivableEntrySheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let onDone: (String) -> Void
    @State private var person = ""
    @State private var text = ""
    @State private var detail = ""
    @State private var kind = "purchase"
    @State private var error: String?
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField(tx("Quién te debe", "Who owes you"), text: $person).accessibilityIdentifier("money.entry.person")
                    TextField(tx("Monto", "Amount"), text: $text).keyboardType(.decimalPad).accessibilityIdentifier("money.entry.amount")
                    Picker(tx("Tipo", "Kind"), selection: $kind) {
                        ForEach(ReceivableEntryRequest.kinds, id: \.self) { Text(Self.kindLabel($0)).tag($0) }
                    }
                    TextField(tx("Detalle (opcional)", "Detail (optional)"), text: $detail).accessibilityIdentifier("money.entry.detail")
                    if let error { Text(error).font(DincrFont.caption).foregroundStyle(DincrColor.negative) }
                }
            }
            .navigationTitle(tx("Nuevo cobro", "New collection"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(tx("Cancelar", "Cancel")) { dismiss() }.disabled(saving) }
                ToolbarItem(placement: .confirmationAction) {
                    Button(tx("Guardar", "Save")) { Task { await submit() } }.disabled(saving).accessibilityIdentifier("money.entry.save")
                }
            }
        }
        .interactiveDismissDisabled(saving)
    }

    static func kindLabel(_ kind: String) -> String {
        switch kind {
        case "purchase": tx("Compra", "Purchase")
        case "loan": tx("Préstamo", "Loan")
        case "transfer": tx("Transferencia", "Transfer")
        case "cash": tx("Efectivo", "Cash")
        default: tx("Otro", "Other")
        }
    }

    private func submit() async {
        guard !saving else { return }
        let name = person.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { error = tx("Escribí quién te debe.", "Enter who owes you."); return }
        guard let amount = AmountInput.parse(text, separators: model.moneyFormat.separators) else {
            error = model.moneyFormat.amountHint
            return
        }
        saving = true; error = nil
        defer { saving = false }
        let epoch = model.currentEpoch
        do {
            try await model.service.addReceivableEntry(ReceivableEntryRequest(personName: name, amount: amount, description: detail.trimmingCharacters(in: .whitespaces), entryKind: kind))
            onDone(tx("Cobro registrado", "Collection recorded"))
            dismiss()
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardarlo. Revisá la lista antes de intentar de nuevo.", "We couldn’t save it. Check the list before trying again."))
        }
    }
}
