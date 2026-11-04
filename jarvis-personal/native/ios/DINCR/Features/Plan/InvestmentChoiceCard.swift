import DincrCore
import DincrDesign
import SwiftUI

/// Plan → Tu plan del mes (VIP): whether investing is in the plan. Off until they turn it on. Turning it
/// on doesn't invest anything: a share appears only when debts and the Salvavidas allow it, and DINCR
/// never picks a stock. Android: `InvestmentChoiceCard`.
struct InvestmentChoiceCard: View {
    @Environment(AppModel.self) private var model
    let changed: () -> Void
    @State private var wanted = false
    @State private var loaded = false
    @State private var error: String?

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Toggle(tx("Incluir inversiones en mi plan", "Include investing in my plan"), isOn: Binding(get: { wanted }, set: { value in Task { await save(value) } }))
                .font(DincrFont.body.weight(.semibold))
                .disabled(!loaded)
                .accessibilityIdentifier("plan.investmentChoice")
            Text(tx("Si lo activás, una parte irá a invertir solo cuando tus deudas y tu Salvavidas lo permitan. DINCR no elige acciones por vos.",
                    "If you turn it on, a share goes to investing only when your debts and emergency fund allow it. DINCR doesn’t pick stocks for you."))
                .font(DincrFont.caption).foregroundStyle(.dincrTextMuted)
            if let error { Text(error).font(DincrFont.caption).foregroundStyle(DincrColor.negative) }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .dincrCard()
        .task {
            if let read = try? await model.service.investmentChoice() { wanted = read.wantsInvesting; loaded = true }
        }
    }

    private func save(_ value: Bool) async {
        let before = wanted
        wanted = value; error = nil
        let epoch = model.currentEpoch
        do {
            wanted = try await model.service.updateInvestmentChoice(InvestmentChoice(wantsInvesting: value)).wantsInvesting
            changed()
        } catch {
            wanted = before
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardar.", "We couldn’t save."))
        }
    }
}
