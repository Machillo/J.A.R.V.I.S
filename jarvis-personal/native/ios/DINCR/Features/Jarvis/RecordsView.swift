import DincrCore
import DincrDesign
import SwiftUI

/// JARVIS → Registros (Owner only): the money timeline (the known incomes and obligations of the
/// next 45 days and the balance they leave) and the account reconciliation (expected against real
/// balance, and "Confirmar saldo real"). Opening it only reads. Every amount is the backend's.
/// Android: `RecordsScreen`.
struct RecordsView: View {
    enum Tab: Hashable { case timeline, reconciliation }

    @Environment(AppModel.self) private var model
    @State private var tab: Tab = .timeline
    @State private var confirming: Reconciliation.Account?
    @State private var notice: String?
    @State private var reloadToken = 0

    var body: some View {
        ScreenScroll(title: tx("Registros", "Records")) {
            Picker(tx("Vista", "View"), selection: $tab) {
                Text(tx("Línea de tiempo", "Timeline")).tag(Tab.timeline)
                Text(tx("Conciliación", "Reconciliation")).tag(Tab.reconciliation)
            }
            .pickerStyle(.segmented)
            .accessibilityIdentifier("records.tab")
            if let notice { StatusBanner(tone: .info, title: notice, message: "").accessibilityIdentifier("records.notice") }
            switch tab {
            case .timeline:
                AsyncContent(fallback: tx("No pudimos cargar tu línea de tiempo.", "We couldn’t load your timeline."),
                             load: { try await model.service.moneyTimeline() }) { timeline, _ in
                    TimelineContent(timeline: timeline)
                }
            case .reconciliation:
                AsyncContent(fallback: tx("No pudimos cargar la conciliación.", "We couldn’t load the reconciliation."),
                             load: { try await model.service.reconciliation() }) { report, _ in
                    ReconciliationContent(report: report, confirm: { confirming = $0 })
                }
                .id(reloadToken)
            }
        }
        .sheet(item: $confirming) { account in
            ConfirmBalanceSheet(account: account) { message in
                notice = message
                reloadToken += 1
            }
        }
    }
}

private struct TimelineContent: View {
    let timeline: MoneyTimeline
    @Environment(\.moneyFormat) private var format

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            FigureRow(label: tx("Disponible hoy", "Available today"), amount: timeline.openingAvailable)
            FigureRow(label: tx("Al final del período", "At the end of the period"), amount: timeline.endingAvailable)
            if let start = timeline.startDate, let end = timeline.endDate {
                Text("\(Day.label(start)) – \(Day.label(end))").font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            }
        }
        .dincrCard()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("records.timeline.summary")

        if timeline.events.isEmpty {
            EmptyStateView(symbol: "calendar", title: tx("Nada programado", "Nothing scheduled"),
                           message: tx("No hay ingresos ni obligaciones con fecha en este período.", "No dated incomes or obligations in this period.")) { EmptyView() }
        }
        ForEach(timeline.days, id: \.date) { day in
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                Text(day.date.isEmpty ? tx("Sin fecha", "No date") : Day.label(day.date)).font(DincrFont.label).foregroundStyle(DincrColor.text2)
                ForEach(day.events) { event in
                    HStack(alignment: .firstTextBaseline) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(event.name ?? tx("Movimiento", "Movement")).font(DincrFont.bodySmall)
                            if let balance = event.projectedBalance {
                                Text(tx("Queda: \(format.string(balance))", "Left: \(format.string(balance))"))
                                    .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                            }
                            if let note = event.note { Text(note).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted) }
                        }
                        Spacer()
                        MoneyText(event.kind == "goal" ? event.amount : event.impact)
                    }
                    .accessibilityElement(children: .combine)
                }
            }
            .dincrCard()
        }
        ForEach(timeline.assumptions, id: \.self) { note in
            Text(note).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
        }
    }
}

private struct ReconciliationContent: View {
    let report: Reconciliation
    let confirm: (Reconciliation.Account) -> Void

    var body: some View {
        if let summary = report.summary {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                if let review = summary.needsReview {
                    Text(review == 0 ? tx("Todas tus cuentas cuadran.", "All your accounts match.")
                                     : review == 1 ? tx("1 cuenta para revisar", "1 account to review") : tx("\(review) cuentas para revisar", "\(review) accounts to review"))
                        .font(DincrFont.bodySmall.weight(.semibold))
                }
                if let unlinked = summary.unlinked, unlinked > 0 {
                    Text(tx("\(unlinked) movimientos sin cuenta asignada", "\(unlinked) movements without an account")).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                }
                if let duplicates = summary.possibleDuplicates, duplicates > 0 {
                    Text(tx("\(duplicates) posibles duplicados para revisar en Movimientos", "\(duplicates) possible duplicates to review in Transactions")).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                }
                if let untracked = summary.untrackedAccounts, untracked > 0 {
                    Text(tx("\(untracked) cuentas sin saldo registrado no se comparan.", "\(untracked) accounts without a recorded balance aren’t compared."))
                        .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                }
                if let note = report.note { Text(note).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted) }
            }
            .dincrCard()
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("records.reconciliation.summary")
        }
        if report.accounts.isEmpty {
            EmptyStateView(symbol: "building.columns", title: tx("No hay cuentas para conciliar", "No accounts to reconcile"),
                           message: tx("Registrá el saldo de tus cuentas para compararlo con tus movimientos.", "Record your accounts’ balances to compare them with your movements.")) { EmptyView() }
        }
        ForEach(report.accounts) { account in
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                HStack(alignment: .firstTextBaseline) {
                    Text([account.accountName, account.last4.map { "••\($0)" }].compactMap { $0 }.joined(separator: " "))
                        .font(DincrFont.body.weight(.semibold))
                    Spacer()
                    Text(account.needsReview ? tx("Revisar", "Review") : tx("Cuadra", "Matches"))
                        .font(DincrFont.caption).foregroundStyle(account.needsReview ? DincrColor.warning : DincrColor.positive)
                }
                FigureRow(label: tx("Saldo esperado", "Expected balance"), amount: account.expectedBalance, currency: account.currency)
                FigureRow(label: tx("Último saldo real", "Last real balance"), amount: account.realBalance, currency: account.currency)
                if account.needsReview { FigureRow(label: tx("Diferencia", "Difference"), amount: account.difference, currency: account.currency) }
                Button(tx("Confirmar saldo real", "Confirm real balance")) { confirm(account) }
                    .buttonStyle(.dincrSecondary)
                    .accessibilityIdentifier("records.confirm.\(account.accountId)")
            }
            .dincrCard()
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("records.account.\(account.accountId)")
        }
    }
}

/// "Confirmar saldo real": the account's balance today, as the Owner checked it in the bank. Sent
/// once (disabled while it is sent), never retried on its own.
private struct ConfirmBalanceSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let account: Reconciliation.Account
    let onDone: (String) -> Void
    @State private var text = ""
    @State private var error: String?
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text(tx("Escribí el saldo que ves hoy en el banco para «\(account.accountName ?? "")» (\(account.currency ?? "CRC")).",
                            "Enter today’s balance you see in the bank for “\(account.accountName ?? "")” (\(account.currency ?? "CRC"))."))
                        .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                    TextField(tx("Saldo real", "Real balance"), text: $text).keyboardType(.decimalPad).accessibilityIdentifier("records.confirm.amount")
                    if let error { Text(error).font(DincrFont.caption).foregroundStyle(DincrColor.negative) }
                }
            }
            .navigationTitle(tx("Confirmar saldo", "Confirm balance"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(tx("Cancelar", "Cancel")) { dismiss() }.disabled(saving) }
                ToolbarItem(placement: .confirmationAction) {
                    Button(tx("Confirmar", "Confirm")) { Task { await submit() } }.disabled(saving).accessibilityIdentifier("records.confirm.save")
                }
            }
        }
        .presentationDetents([.medium])
        .interactiveDismissDisabled(saving)
    }

    private func submit() async {
        guard !saving else { return }
        // The balance is never guessed: an empty or invalid field is not sent (as on Android).
        guard let amount = AmountInput.parse(text, separators: model.moneyFormat.separators) else {
            error = model.moneyFormat.amountHint
            return
        }
        saving = true; error = nil
        defer { saving = false }
        let epoch = model.currentEpoch
        do {
            try await model.service.confirmReconciliation(accountID: account.accountId, ReconciliationConfirmRequest(realBalance: amount))
            onDone(tx("Saldo confirmado", "Balance confirmed"))
            dismiss()
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos confirmarlo. Revisá la conciliación antes de intentar de nuevo.", "We couldn’t confirm it. Check the reconciliation before trying again."))
        }
    }
}
