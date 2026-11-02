import DincrCore
import DincrDesign
import SwiftUI

/// After an extra payment the bank may shorten the term or lower the installment, and sometimes says
/// it days later. Debts waiting for that answer ("El banco me avisa después", or a confirmed
/// distribution) are listed above the debts; "Ya me dijo" answers: installments left, the new
/// installment, nothing changed, or another day to be reminded (`POST …/after-extra`). Nothing is
/// guessed. Android twin: `DebtAfterExtra.kt`.
struct WaitingForBankCard: View {
    let debts: [Debt]
    let waiting: [String: DebtAfterExtraPending]
    let canWrite: Bool
    let answer: (Debt) -> Void

    var body: some View {
        let rows = debts.filter { waiting[String($0.id)] != nil }
        if !rows.isEmpty {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                SectionHeader(title: tx("Esperando al banco", "Waiting for the bank"))
                Text(tx("Abonaste extra: contanos si el banco bajó el plazo o la cuota.", "You paid extra: tell us whether the bank shortened the term or lowered the installment."))
                    .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                ForEach(rows) { debt in
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(debt.name ?? "").font(DincrFont.title2)
                            if let day = waiting[String(debt.id)]?.remindOn {
                                Text(tx("Te avisamos el \(DebtSavingsReading.dayLabel(day))", "We remind you on \(DebtSavingsReading.dayLabel(day))"))
                                    .font(DincrFont.caption).foregroundStyle(DincrColor.text2)
                            }
                        }
                        Spacer()
                        if canWrite {
                            Button(tx("Ya me dijo", "It told me")) { answer(debt) }
                                .buttonStyle(.dincrSecondary)
                                .accessibilityIdentifier("debts.afterExtra.\(debt.id)")
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .dincrCard()
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("debts.waitingForBank")
        }
    }
}

/// What the bank did with the extra payment, or another day to be reminded.
struct AfterExtraSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let debt: Debt
    let done: (String) -> Void
    @State private var choice = Choice.shorterTerm
    @State private var figure = ""
    @State private var day = Calendar.current.date(byAdding: .day, value: 3, to: Date()) ?? Date()
    @State private var error: String?
    @State private var saving = false

    enum Choice: Hashable { case shorterTerm, lowerInstallment, unchanged, later }

    var body: some View {
        NavigationStack {
            Form {
                Text(debt.name ?? "").font(DincrFont.title2)
                Picker(tx("¿Qué hizo el banco?", "What did the bank do?"), selection: $choice) {
                    Text(tx("Bajó el plazo", "Shortened the term")).tag(Choice.shorterTerm)
                    Text(tx("Bajó la cuota", "Lowered the installment")).tag(Choice.lowerInstallment)
                    Text(tx("Nada cambió", "Nothing changed")).tag(Choice.unchanged)
                    Text(tx("Todavía no sé", "I don't know yet")).tag(Choice.later)
                }
                .accessibilityIdentifier("debts.afterExtra.choice")
                switch choice {
                case .shorterTerm:
                    TextField(tx("Cuotas que te quedan", "Installments left"), text: $figure).keyboardType(.numberPad)
                        .accessibilityIdentifier("debts.afterExtra.remaining")
                case .lowerInstallment:
                    TextField(tx("Cuota nueva", "New installment"), text: $figure).keyboardType(.decimalPad)
                        .accessibilityIdentifier("debts.afterExtra.installment")
                case .later:
                    DatePicker(tx("Recordarme el", "Remind me on"), selection: $day, in: Date()..., displayedComponents: .date)
                case .unchanged:
                    EmptyView()
                }
                if let error { Text(error).foregroundStyle(DincrColor.negative) }
            }
            .navigationTitle(tx("Tu abono extra", "Your extra payment"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(tx("Cancelar", "Cancel")) { dismiss() }.disabled(saving) }
                ToolbarItem(placement: .confirmationAction) {
                    Button(tx("Guardar", "Save")) { Task { await save() } }.disabled(saving).accessibilityIdentifier("debts.afterExtra.save")
                }
            }
        }
        .interactiveDismissDisabled(saving)
    }

    private func save() async {
        let answer: DebtAfterExtraAnswer
        switch choice {
        case .shorterTerm:
            guard let count = Int(figure.trimmingCharacters(in: .whitespaces)), (1...600).contains(count) else {
                error = tx("Escribí cuántas cuotas te quedan.", "Enter how many installments are left."); return
            }
            answer = .remainingInstallments(count)
        case .lowerInstallment:
            guard let value = AmountInput.parse(figure, separators: model.moneyFormat.separators), value > 0 else {
                error = tx("Escribí la cuota nueva.", "Enter the new installment."); return
            }
            answer = .newMonthlyPayment(value)
        case .unchanged:
            answer = .unchanged
        case .later:
            answer = .remindOn(MovementEditor.dayFormatter.string(from: day))
        }
        saving = true; error = nil
        defer { saving = false }
        let epoch = model.currentEpoch
        do {
            try await model.service.answerAfterExtra(debtID: debt.id, answer)
            dismiss()
            done(choice == .later ? tx("Te lo recordamos ese día", "We'll remind you that day") : tx("Deuda actualizada", "Debt updated"))
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardar.", "We couldn’t save."))
        }
    }
}
