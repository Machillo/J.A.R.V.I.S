import DincrCore
import DincrDesign
import SwiftUI

/// DB-1 — Plan → Ahorro para deudas (Owner only): the next locked savings block the strategy proposes
/// (which debt, how much every Thursday, for how long, what locking costs) and the blocks already
/// created at the bank, with their progress. The backend decides every number
/// (`GET /jarvis/premium/debt-savings-blocks`); "Ya lo creé en el banco" records a block (POST) and
/// "Quitar" removes one (DELETE): both are the Owner's explicit actions. Android twin:
/// `DebtSavingsBlocksScreen.kt`.
struct DebtSavingsBlocksView: View {
    @Environment(AppModel.self) private var model
    @State private var generation = 0
    @State private var creating: DebtSavingsBlocks.Proposal?
    @State private var removing: DebtSavingsBlocks.Block?
    @State private var error: String?

    var body: some View {
        ScreenScroll(title: tx("Ahorro para deudas", "Savings for debts")) {
            AsyncContent(load: { try await model.service.debtSavingsBlocks() }) { state, _ in
                content(state)
            }
            .id(generation)
            FinancialDisclaimer()
        }
        .sheet(item: Binding(get: { creating.map(ProposalItem.init) }, set: { if $0 == nil { creating = nil } })) { item in
            CreateBlockSheet(proposal: item.proposal) { creating = nil; generation += 1 }
        }
        .confirmationDialog(tx("¿Quitar este ahorro?", "Remove this saving?"),
                            isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } }), titleVisibility: .visible) {
            Button(tx("Quitar", "Remove"), role: .destructive) { if let block = removing { Task { await remove(block) } } }
            Button(tx("Cancelar", "Cancel"), role: .cancel) {}
        } message: {
            Text(tx("Se quita de DINCR y tu plan deja de apartarlo. En el banco sigue como esté.", "It is removed from DINCR and your plan stops setting it aside. At the bank it stays as it is."))
        }
    }

    @ViewBuilder
    private func content(_ state: DebtSavingsBlocks) -> some View {
        let format = model.moneyFormat
        if let error { DincrMessage(.technicalError, title: tx("No se pudo quitar", "Couldn’t remove"), message: error) }
        if let proposal = state.proposal {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                SectionHeader(title: tx("Tu próximo ahorro", "Your next saving"))
                Text(DebtSavingsReading.headline(proposal, format: format)).font(DincrFont.title2)
                    .accessibilityIdentifier("debtBlocks.headline")
                ForEach(Array(DebtSavingsReading.lines(state, format: format).enumerated()), id: \.offset) { _, line in
                    Text(line).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2).fixedSize(horizontal: false, vertical: true)
                }
                Text(DebtSavingsReading.recommendation(proposal)).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                    .fixedSize(horizontal: false, vertical: true)
                if model.flags.isEnabled(.financialWrites) {
                    Button(tx("Ya lo creé en el banco", "I created it at the bank")) { creating = proposal }
                        .buttonStyle(.dincrPrimary)
                        .accessibilityIdentifier("debtBlocks.create")
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .dincrCard()
            .accessibilityIdentifier("debtBlocks.proposal")
        } else if let message = DebtSavingsReading.statusMessage(state) {
            Text(message).font(DincrFont.body).frame(maxWidth: .infinity, alignment: .leading).dincrCard()
                .accessibilityIdentifier("debtBlocks.status")
        }
        ForEach(DebtSavingsReading.warnings(state), id: \.self) { warning in
            Text(warning).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted).frame(maxWidth: .infinity, alignment: .leading)
        }
        if let blocks = state.blocks, !blocks.isEmpty {
            VStack(alignment: .leading, spacing: DincrSpacing.s3) {
                SectionHeader(title: tx("Tus ahorros bloqueados", "Your locked savings"))
                ForEach(blocks) { block in
                    VStack(alignment: .leading, spacing: DincrSpacing.s1) {
                        Text(block.debtName ?? tx("Deuda", "Debt")).font(DincrFont.title2)
                        ForEach(Array(DebtSavingsReading.blockLines(block, format: format).enumerated()), id: \.offset) { _, line in
                            Text(line).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2).fixedSize(horizontal: false, vertical: true)
                        }
                        if model.flags.isEnabled(.financialWrites) {
                            Button(tx("Quitar", "Remove"), role: .destructive) { removing = block }
                                .font(DincrFont.caption)
                                .accessibilityIdentifier("debtBlocks.remove.\(block.id)")
                        }
                    }
                    .accessibilityIdentifier("debtBlocks.block.\(block.id)")
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .dincrCard()
        }
    }

    private func remove(_ block: DebtSavingsBlocks.Block) async {
        let epoch = model.currentEpoch
        do {
            try await model.service.cancelDebtSavingsBlock(id: block.id)
            error = nil
            generation += 1
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("Intentalo de nuevo.", "Try again."))
        }
        removing = nil
    }
}

private struct ProposalItem: Identifiable {
    let proposal: DebtSavingsBlocks.Proposal
    var id: String { "\(proposal.debt?.id ?? 0)-\(proposal.startDate ?? "")" }
}

/// What was created at the bank: prefilled with the proposal; the Owner corrects what the bank set.
private struct CreateBlockSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let proposal: DebtSavingsBlocks.Proposal
    let saved: () -> Void
    @State private var weekly = ""
    @State private var months = ""
    @State private var start = Date()
    @State private var error: String?
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                Text(proposal.debt?.name ?? "").font(DincrFont.title2)
                MoneyField(label: tx("Cada jueves", "Every Thursday"), text: $weekly, identifier: "debtBlocks.weekly")
                TextField(tx("Meses (3 o más)", "Months (3 or more)"), text: $months).keyboardType(.numberPad)
                    .accessibilityIdentifier("debtBlocks.months")
                DatePicker(tx("Primer ahorro", "First saving"), selection: $start, displayedComponents: .date)
                if let error { Text(error).foregroundStyle(DincrColor.negative) }
            }
            .navigationTitle(tx("Ahorro creado", "Saving created"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(tx("Cancelar", "Cancel")) { dismiss() }.disabled(saving) }
                ToolbarItem(placement: .confirmationAction) {
                    Button(tx("Guardar", "Save")) { Task { await save() } }.disabled(saving).accessibilityIdentifier("debtBlocks.save")
                }
            }
            .onAppear(perform: prefill)
        }
        .interactiveDismissDisabled(saving)
    }

    private func prefill() {
        weekly = proposal.weeklyAmount.map(model.moneyFormat.inputText) ?? ""
        months = proposal.termMonths.map(String.init) ?? ""
        if let day = proposal.startDate, let parsed = MovementEditor.dayFormatter.date(from: String(day.prefix(10))) { start = parsed }
    }

    private func save() async {
        guard let debtId = proposal.debt?.id else { return }
        guard let amount = AmountInput.parse(weekly, separators: model.moneyFormat.separators), amount > 0 else {
            error = model.moneyFormat.amountHint; return
        }
        guard let term = Int(months.trimmingCharacters(in: .whitespaces)), (3...60).contains(term) else {
            error = tx("El plazo va de 3 a 60 meses.", "The term is 3 to 60 months."); return
        }
        saving = true; error = nil
        defer { saving = false }
        let epoch = model.currentEpoch
        do {
            try await model.service.createDebtSavingsBlock(DebtSavingsBlockCreate(
                debtId: debtId, weeklyAmount: amount, startDate: MovementEditor.dayFormatter.string(from: start), termMonths: term, mode: proposal.mode))
            dismiss()
            saved()
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardar.", "We couldn’t save."))
        }
    }
}
