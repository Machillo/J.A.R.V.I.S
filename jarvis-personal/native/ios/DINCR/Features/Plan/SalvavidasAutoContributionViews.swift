import DincrCore
import DincrDesign
import SwiftUI

/// Salvavidas automatic contributions (VIP and the Owner): what the plan added under the balance,
/// and the form that saves it. Every figure is the backend's (`auto_contribution`); the app only
/// sends the plan the user ticked and filled. The interest rate is offered to the Owner scope only.
/// Android twin: `SalvavidasAutoContribution.kt`.
struct SalvavidasPlanBreakdown: View {
    let fund: Salvavidas

    var body: some View {
        if let plan = fund.activePlan {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                FigureRow(label: tx("Saldo declarado", "Declared balance"), amount: fund.declaredAmount ?? plan.baseAmount)
                FigureRow(label: SalvavidasAutoContribution.countLabel(plan.contributionsCount ?? 0), amount: plan.contributionsAmount ?? 0)
                    .accessibilityIdentifier("salvavidas.breakdown.contributions")
                if fund.isOwnerScope {
                    FigureRow(label: tx("Intereses estimados", "Estimated interest"), amount: plan.estimatedInterest ?? 0)
                        .accessibilityIdentifier("salvavidas.breakdown.interest")
                }
                if let next = plan.nextDate {
                    InfoRow(label: tx("Próximo aporte", "Next contribution"), value: Day.label(next))
                        .accessibilityIdentifier("salvavidas.breakdown.next")
                }
            }
            .padding(.top, DincrSpacing.s1)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("salvavidas.breakdown")
        }
    }
}

/// "Aportes automáticos": a box to tick (the plan works only when ticked), the amount, frequency,
/// first and optional last date; the balance of today while the savings are unknown (0 allowed);
/// and, for the Owner only, the annual interest rate. One PUT per tap of Guardar. A saved, active
/// plan shows as one line with "Editar"; the form opens only to change it.
struct AutoContributionCard: View {
    @Environment(AppModel.self) private var model
    let fund: Salvavidas
    let canWrite: Bool
    let saving: Bool
    /// Returns an error to show, or nil when saved.
    let save: (SalvavidasUpdate) async -> String?

    @State private var enabled = false
    @State private var amount = ""
    @State private var frequency = "monthly"
    @State private var start = Date.now
    @State private var hasEnd = false
    @State private var end = Date.now
    @State private var savedToday = ""
    @State private var rate = ""
    @State private var error: String?
    @State private var editing = false

    /// A saved, active plan is summarized until the user taps "Editar".
    private var summarized: Bool { fund.activePlan != nil && !editing }
    /// While the savings are unknown, turning the plan on needs the balance of today.
    private var asksBalance: Bool { enabled && !fund.savingsKnown }
    private var showsFields: Bool { enabled || fund.autoContribution != nil }

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s3) {
            SectionHeader(title: tx("Aportes automáticos", "Automatic contributions"))
            if summarized, let plan = fund.activePlan {
                PlanSummary(fund: fund, plan: plan)
                if canWrite {
                    Button(tx("Editar aportes", "Edit contributions")) { editing = true }
                        .buttonStyle(.dincrSecondary)
                        .disabled(saving)
                        .accessibilityIdentifier("salvavidas.auto.edit")
                }
            } else {
                form
            }
        }
        .dincrCard()
        // The decimal pad has no return key: "Listo" closes it so "Guardar aportes" is reachable.
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button(tx("Listo", "Done")) { UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil) }
                    .accessibilityIdentifier("salvavidas.auto.keyboardDone")
            }
        }
        .onAppear(perform: prefill)
        .onChange(of: fund) { prefill() }
    }

    @ViewBuilder private var form: some View {
            Text(tx("Si un monto fijo entra a tu Salvavidas (por ejemplo, una transferencia automática), DINCR lo suma a tu saldo según el plan.",
                    "If a fixed amount goes into your emergency fund (for example, an automatic transfer), DINCR adds it to your balance following the plan."))
                .font(DincrFont.caption).foregroundStyle(DincrColor.text2)
            Toggle(tx("Activar aportes automáticos", "Turn on automatic contributions"), isOn: $enabled)
                .tint(DincrColor.tint)
                .disabled(!canWrite || saving)
                .accessibilityIdentifier("salvavidas.auto.enabled")
            if showsFields {
                MoneyField(label: tx("Monto por aporte", "Amount per contribution"), text: $amount, identifier: "salvavidas.auto.amount")
                VStack(alignment: .leading, spacing: DincrSpacing.s1) {
                    Text(tx("Frecuencia", "Frequency")).font(DincrFont.label).foregroundStyle(DincrColor.text2)
                    Picker(tx("Frecuencia", "Frequency"), selection: $frequency) {
                        ForEach(SalvavidasAutoContribution.frequencies, id: \.self) { value in
                            Text(SalvavidasAutoContribution.frequencyLabel(value)).tag(value)
                        }
                    }
                    .pickerStyle(.segmented)
                    .accessibilityIdentifier("salvavidas.auto.frequency")
                }
                DatePicker(tx("Primer aporte", "First contribution"), selection: $start, displayedComponents: .date)
                    .accessibilityIdentifier("salvavidas.auto.start")
                Toggle(tx("Tiene fecha final", "Has an end date"), isOn: $hasEnd)
                    .tint(DincrColor.tint)
                    .accessibilityIdentifier("salvavidas.auto.hasEnd")
                if hasEnd {
                    DatePicker(tx("Termina", "Ends"), selection: $end, in: start..., displayedComponents: .date)
                        .accessibilityIdentifier("salvavidas.auto.end")
                }
                if asksBalance {
                    MoneyField(label: tx("¿Cuánto tenés ahorrado hoy? (puede ser 0)", "How much do you have saved today? (it can be 0)"),
                               text: $savedToday, identifier: "salvavidas.auto.current")
                }
            }
            if fund.offersInterestRate {
                VStack(alignment: .leading, spacing: DincrSpacing.s1) {
                    Text(tx("Interés anual ganado (%)", "Annual interest earned (%)")).font(DincrFont.label).foregroundStyle(DincrColor.text2)
                    TextField(tx("Interés anual ganado (%)", "Annual interest earned (%)"), text: $rate, prompt: Text("2,5"))
                        .keyboardType(.decimalPad)
                        .font(DincrFont.body.monospacedDigit())
                        .accessibilityIdentifier("salvavidas.auto.rate")
                    Text(tx("Estimamos los intereses con esta tasa; el banco acredita los reales.",
                            "We estimate the interest with this rate; your bank credits the real one."))
                        .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                }
            }
            if let error {
                Label(error, systemImage: "exclamationmark.circle").font(DincrFont.caption).foregroundStyle(DincrColor.negative)
                    .accessibilityIdentifier("salvavidas.auto.error")
            }
            if canWrite && (showsFields || fund.offersInterestRate) {
                Button(tx("Guardar aportes", "Save contributions")) { Task { await submit() } }
                    .buttonStyle(.dincrPrimary)
                    .disabled(saving)
                    .accessibilityIdentifier("salvavidas.auto.save")
            }
            if editing {
                Button(tx("Cancelar", "Cancel")) { prefill() }
                    .buttonStyle(.dincrSecondary)
                    .disabled(saving)
                    .accessibilityIdentifier("salvavidas.auto.cancel")
            }
    }

    /// The saved plan (or defaults); called on load and after every answer of the backend.
    private func prefill() {
        let plan = fund.autoContribution
        enabled = plan?.isEnabled ?? false
        amount = plan?.amount.map(model.moneyFormat.inputText) ?? ""
        frequency = SalvavidasAutoContribution.frequencies.contains(plan?.frequency ?? "") ? plan!.frequency! : "monthly"
        start = plan?.startDate.flatMap { Day.formatter().date(from: String($0.prefix(10))) } ?? .now
        let endDay = plan?.endDate.flatMap { Day.formatter().date(from: String($0.prefix(10))) }
        hasEnd = endDay != nil
        end = endDay ?? start
        savedToday = ""
        rate = fund.annualInterestRate.map { "\($0)".replacingOccurrences(of: ".", with: model.moneyFormat.separators == .dotComma ? "," : ".") } ?? ""
        error = nil
        editing = false
    }

    private func submit() async {
        let separators = model.moneyFormat.separators
        var plan: SalvavidasPlanRequest?
        if showsFields {
            guard let value = AmountInput.parse(amount, separators: separators) else { error = model.moneyFormat.amountHint; return }
            let formatter = Day.formatter()
            let endDay = hasEnd ? formatter.string(from: max(end, start)) : nil
            plan = SalvavidasPlanRequest(enabled: enabled, amount: value, frequency: frequency, startDate: formatter.string(from: start), endDate: endDay)
        }
        var balance: Decimal?
        if asksBalance {
            guard let value = AmountInput.parseZeroOrMore(savedToday, separators: separators) else {
                error = tx("Indicá cuánto tenés ahorrado hoy (puede ser 0) para activar los aportes automáticos.",
                           "Enter how much you have saved today (it can be 0) to turn on automatic contributions.")
                return
            }
            balance = value
        }
        var annual: Decimal?
        if fund.offersInterestRate, !rate.trimmingCharacters(in: .whitespaces).isEmpty {
            guard let value = SalvavidasRateInput.parse(rate) else {
                error = tx("Indicá una tasa de interés anual entre 0 % y 50 %.", "Enter an annual interest rate between 0% and 50%.")
                return
            }
            if value != fund.annualInterestRate { annual = value }
        }
        guard let update = SalvavidasUpdate.plan(plan, currentAmount: balance, annualInterestRate: annual) else {
            error = tx("No hay cambios para guardar.", "There are no changes to save.")
            return
        }
        error = nil
        if let failure = await save(update) { error = failure }
    }
}

/// One line for a saved, active plan: "₡2.500 cada semana · desde 5 nov 2026", the end and, for the
/// Owner, the rate.
private struct PlanSummary: View {
    @Environment(AppModel.self) private var model
    let fund: Salvavidas
    let plan: SalvavidasAutoContribution

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s1) {
            Text(SalvavidasAutoContribution.summary(amount: model.moneyFormat.string(plan.amount ?? 0), frequency: plan.frequency))
                .font(DincrFont.body)
                .accessibilityIdentifier("salvavidas.auto.summary")
            if let start = plan.startDate {
                InfoRow(label: tx("Desde", "From"), value: Day.label(start))
            }
            if let end = plan.endDate {
                InfoRow(label: tx("Hasta", "Until"), value: Day.label(end))
            }
            if fund.isOwnerScope, let rate = fund.annualInterestRate {
                InfoRow(label: tx("Interés anual", "Annual interest"), value: SalvavidasAutoContribution.rateLabel(rate))
            }
        }
    }
}
