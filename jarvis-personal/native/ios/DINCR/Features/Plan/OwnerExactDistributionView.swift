import DincrCore
import DincrDesign
import SwiftUI

// Plan → Distribución de dinero, Owner only. The MODE says where the money to split comes from
// (DINCR's estimate, or the amount the Owner has left after paying everything, split whole: no
// obligation is deducted from it again); the STRATEGY (the backend's Director engine) decides how it
// is split, the same in both. Calculating an exact amount is a plan: the backend writes nothing
// (POST /jarvis/premium/strategy-dashboard/exact-distribution). CONFIRMAR is the Owner declaring he
// carried it out: the backend records the debt payments, the Salvavidas deposit and the other
// destinations once (POST .../exact-distribution/confirm). Both are refused to anyone but the Owner.
// Android: OwnerExactDistribution.kt.

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
    @State private var confirming = false
    @State private var asking = false
    /// The estimate read again after a confirmation changed the records.
    @State private var refreshedEstimate: DashboardStrategy?

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
            DashboardDistribution(plan: refreshedEstimate ?? estimate)
        case .exact:
            VStack(alignment: .leading, spacing: DincrSpacing.s3) {
                Text(tx("Indicá cuánto dinero te sobra después de pagar tus gastos, tarjetas y cuotas. DINCR reparte ese monto completo con tu estrategia actual, sin volver a descontar esos pagos. Calcular no registra nada: solo CONFIRMAR registra los movimientos.",
                        "Enter how much money you have left after paying your expenses, cards and instalments. DINCR splits that whole amount with your current strategy, without deducting those payments again. Calculating records nothing: only CONFIRM records the movements."))
                    .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                MoneyField(label: tx("Monto que te sobra, en colones", "Amount you have left, in colones"), text: Binding(get: { form.amountText }, set: { form.edit($0) }),
                           error: form.error, identifier: "distribution.exact.amount")
                Button {
                    Task { await calculate() }
                } label: {
                    Text(form.result == nil ? tx("Calcular distribución", "Calculate distribution") : tx("Actualizar distribución", "Update distribution"))
                }
                .buttonStyle(.dincrPrimary)
                .disabled(loading || confirming)
                .accessibilityIdentifier("distribution.exact.calculate")
            }
            .dincrCard()
            if let result = form.result { ExactDistributionResult(form: form, plan: result) }
            if form.canConfirm {
                Button { asking = true } label: { Text(tx("CONFIRMAR", "CONFIRM")) }
                    .buttonStyle(.dincrPrimary)
                    .disabled(confirming)
                    .accessibilityIdentifier("distribution.exact.confirm")
                    .confirmationDialog(tx("¿Ya hiciste estos movimientos?", "Did you already make these movements?"),
                                        isPresented: $asking, titleVisibility: .visible) {
                        Button(tx("Confirmar", "Confirm")) { Task { await confirm() } }
                        Button(tx("Cancelar", "Cancel"), role: .cancel) {}
                    } message: {
                        Text(tx("Al confirmar, DINCR registra los abonos, el ahorro y los demás destinos de esta distribución, y tus saldos cambian. Confirmá solo si ya moviste el dinero así.",
                                "When you confirm, DINCR records the payments, the savings and the other destinations of this distribution, and your balances change. Confirm only if you already moved the money this way."))
                    }
            }
        }
    }

    private func confirm() async {
        guard let key = form.confirmationKey,
              let amount = AmountInput.parse(form.amountText, separators: model.moneyFormat.separators),
              let request = form.confirmRequest(amount: amount) else { return }
        confirming = true
        defer { confirming = false }
        let epoch = model.currentEpoch
        do {
            let answer = try await model.service.ownerConfirmExactDistribution(request)
            form.confirmed(key: key, answer)
            // The records changed: the estimate is read again (a failure keeps the previous one).
            refreshedEstimate = (try? await model.service.ownerStrategyDashboard())?.strategy ?? refreshedEstimate
        } catch {
            form.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos saber si se registró. Volvé a presionar CONFIRMAR: si ya se registró, no se repite.",
                                                                            "We couldn’t tell whether it was recorded. Press CONFIRM again: if it was already recorded, it isn’t repeated."))
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
            let answer = try await model.service.ownerExactDistribution(amount: amount)
            form.calculated(for: typed, answer.strategy, plan: answer.confirmationPlan)
        } catch {
            guard form.amountText == typed else { return }  // an error for an amount no longer on screen
            form.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos calcular la distribución.", "We couldn’t calculate the distribution."))
        }
    }
}

private struct ExactDistributionResult: View {
    let form: ExactDistributionForm
    let plan: DashboardStrategy

    var body: some View {
        if form.confirmation != nil {
            DincrMessage(.positive, title: tx("Distribución confirmada", "Distribution confirmed"),
                         message: tx("Se registraron los abonos, el ahorro y los demás destinos. Tus deudas, tu Salvavidas y tu estrategia ya lo reflejan.",
                                     "The payments, the savings and the other destinations were recorded. Your debts, Salvavidas and strategy already show it."))
        } else {
            StatusBanner(tone: .info, title: tx("Calculado con el monto que indicaste", "Calculated from the amount you entered"),
                         message: tx("Todavía no se registró nada. Si ya moviste el dinero así, presioná CONFIRMAR.",
                                     "Nothing has been recorded yet. If you already moved the money this way, press CONFIRM."))
        }
        ForEach(Array((plan.distributionWarnings ?? []).enumerated()), id: \.offset) { _, warning in
            DincrMessage(.attention, title: tx("Dato incompleto", "Incomplete data"), message: warning.message ?? "")
        }
        DashboardDistribution(plan: plan)
        if let confirmation = form.plan {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                SectionHeader(title: form.confirmation != nil ? tx("Lo que se registró", "What was recorded")
                                                             : tx("Lo que se registrará al confirmar", "What CONFIRM will record"))
                ForEach(Array(confirmation.steps.enumerated()), id: \.offset) { _, step in
                    ConfirmationStepRows(step: step)
                }
            }
            .dincrCard()
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("distribution.exact.plan")
            ForEach(Array(confirmation.blockingReasons.enumerated()), id: \.offset) { _, reason in
                DincrMessage(.attention, title: tx("No se puede confirmar", "It can’t be confirmed"), message: reason)
            }
        }
    }
}

private struct ConfirmationStepRows: View {
    let step: ConfirmationPlan.Step

    var body: some View {
        switch step.action {
        case "debt_extra_payment":
            ForEach(Array(step.targets.enumerated()), id: \.offset) { _, target in
                FigureRow(label: tx("Abono a \(target.name ?? "")", "Payment to \(target.name ?? "")"), amount: target.amount)
            }
        case "salvavidas_deposit":
            FigureRow(label: tx("Depósito al Salvavidas", "Deposit to the Salvavidas"), amount: step.amount)
        case "goal_contribution":
            FigureRow(label: tx("Aporte a \(step.goalName ?? "")", "Contribution to \(step.goalName ?? "")"), amount: step.amount)
        case "investment_reserve":
            FigureRow(label: tx("Reservado para invertir", "Reserved to invest"), amount: step.amount)
        default:
            FigureRow(label: tx("Para vivir (no se registra: tus gastos se registran cuando ocurren)", "To live on (not recorded: spending is recorded when it happens)"), amount: step.amount)
        }
    }
}
