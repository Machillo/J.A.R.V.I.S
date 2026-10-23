import DincrCore
import DincrDesign
import SwiftUI

// Plan → Distribución de dinero, Owner only (phase 1). The MODE says where the money to split comes
// from (DINCR's estimate, or the amount the Owner has left after paying everything, split whole: no
// obligation is deducted from it again); the STRATEGY (the backend's Director
// engine) decides how it is split, the same in both. The exact amount is a plan: the backend writes
// and stores nothing (POST /jarvis/premium/strategy-dashboard/exact-distribution, refused to anyone
// but the Owner). Android: OwnerExactDistribution.kt.

struct OwnerDistributionModes: View {
    enum Mode: Hashable { case estimate, exact }

    /// The backend's ceiling for a confirmed amount (backend/ai/models.py EXACT_DISTRIBUTION_MAX).
    static let maxAmount = Decimal(1_000_000_000)

    @Environment(AppModel.self) private var model
    let estimate: DashboardStrategy
    @State private var mode: Mode = .estimate
    /// Amount, result and error together: editing the amount drops a result calculated from another.
    @State private var form = ExactDistributionForm()
    @State private var loading = false

    var body: some View {
        Picker(tx("Tipo de distribución", "Distribution type"), selection: $mode) {
            Text(tx("Aproximada", "Estimated")).tag(Mode.estimate)
            Text(tx("Monto exacto", "Exact amount")).tag(Mode.exact)
        }
        .pickerStyle(.segmented)
        .accessibilityIdentifier("distribution.mode")

        switch mode {
        case .estimate:
            StatusBanner(tone: .info, title: tx("Distribución aproximada", "Estimated distribution"),
                         message: tx("Calculada con tus registros en DINCR. Puede diferir del dinero que realmente tenés.",
                                     "Calculated from your records in DINCR. It may differ from the money you really have."))
            DashboardDistribution(plan: estimate)
        case .exact:
            VStack(alignment: .leading, spacing: DincrSpacing.s3) {
                Text(tx("Indicá cuánto dinero te sobra después de pagar tus gastos, tarjetas y cuotas. DINCR reparte ese monto completo con tu estrategia actual, sin volver a descontar esos pagos. No registra movimientos ni cambia tus saldos.",
                        "Enter how much money you have left after paying your expenses, cards and instalments. DINCR splits that whole amount with your current strategy, without deducting those payments again. It records no movement and changes no balance."))
                    .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                MoneyField(label: tx("Monto que te sobra, en colones", "Amount you have left, in colones"), text: Binding(get: { form.amountText }, set: { form.edit($0) }),
                           error: form.error, identifier: "distribution.exact.amount")
                Button {
                    Task { await calculate() }
                } label: {
                    Text(form.result == nil ? tx("Calcular distribución", "Calculate distribution") : tx("Actualizar distribución", "Update distribution"))
                }
                .buttonStyle(.dincrPrimary)
                .disabled(loading)
                .accessibilityIdentifier("distribution.exact.calculate")
            }
            .dincrCard()
            if let result = form.result { ExactDistributionResult(plan: result) }
        }
    }

    private func calculate() async {
        let typed = form.amountText
        guard let amount = AmountInput.parse(typed, separators: model.moneyFormat.separators) else {
            form.error = tx("Escribí un monto mayor que cero, con hasta dos decimales.", "Enter an amount above zero, with up to two decimals.")
            return
        }
        guard amount <= Self.maxAmount else {
            form.error = tx("El monto no puede superar ₡1.000.000.000.", "The amount can’t exceed ₡1,000,000,000.")
            return
        }
        loading = true
        form.error = nil
        defer { loading = false }
        let epoch = model.currentEpoch
        do {
            let strategy = try await model.service.ownerExactDistribution(amount: amount).strategy
            form.calculated(for: typed, strategy)
        } catch {
            guard form.amountText == typed else { return }  // an error for an amount no longer on screen
            form.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos calcular la distribución.", "We couldn’t calculate the distribution."))
        }
    }
}

private struct ExactDistributionResult: View {
    let plan: DashboardStrategy

    var body: some View {
        StatusBanner(tone: .info, title: tx("Calculado con el monto que indicaste", "Calculated from the amount you entered"),
                     message: tx("Es un plan: no se registró ningún movimiento ni cambió ningún saldo.",
                                 "It’s a plan: no movement was recorded and no balance changed."))
        ForEach(Array((plan.distributionWarnings ?? []).enumerated()), id: \.offset) { _, warning in
            DincrMessage(.attention, title: tx("Dato incompleto", "Incomplete data"), message: warning.message ?? "")
        }
        DashboardDistribution(plan: plan)
    }
}
