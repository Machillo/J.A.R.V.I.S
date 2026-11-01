import DincrCore
import DincrDesign
import SwiftUI

/// What the user wants to try in Escenarios (VIP). The debt ones answer how much would be left each
/// month after essentials and debt payments (`POST /finance/strategy-vip/debt-scenario`); nothing is
/// saved. Same choices as Android's `ScenarioChoice`.
enum ScenarioChoice: String, CaseIterable, Identifiable {
    case general, payOff, extraPayment, newDebt, refinance, consolidate
    var id: String { rawValue }

    var title: String {
        switch self {
        case .general: tx("Cambiar ingresos o gastos", "Change income or expenses")
        case .payOff: tx("Pagar una deuda completa", "Pay a debt off")
        case .extraPayment: tx("Abonar a una deuda", "Make an extra payment to a debt")
        case .newDebt: tx("Agregar una deuda nueva", "Add a new debt")
        case .refinance: tx("Refinanciar una deuda", "Refinance a debt")
        case .consolidate: tx("Juntar deudas en un préstamo", "Consolidate debts into one loan")
        }
    }
}

struct ScenarioChoicePicker: View {
    @Binding var choice: ScenarioChoice

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Text(tx("¿Qué querés probar?", "What do you want to try?")).font(DincrFont.body.weight(.semibold))
            Picker(tx("Escenario", "Scenario"), selection: $choice) {
                ForEach(ScenarioChoice.allCases) { Text($0.title).tag($0) }
            }
            .pickerStyle(.menu)
            .accessibilityIdentifier("scenario.kind")
        }
        .dincrCard()
    }
}

/// Pay off, extra payment or new debt: the inputs for the chosen what-if, then its answer.
struct DebtScenarioForm: View {
    let choice: ScenarioChoice
    @Environment(AppModel.self) private var model
    @State private var debts: [Debt]?
    @State private var debtId: Int?
    @State private var amount = ""
    @State private var name = ""
    @State private var payment = ""
    @State private var rate = ""
    @State private var term = ""
    @State private var fee = ""
    @State private var chosen: Set<Int> = []
    @State private var result: DebtScenarioResult?
    @State private var error: String?
    @State private var running = false

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s3) {
            Text(intro).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
            if choice == .newDebt {
                TextField(tx("Nombre (opcional)", "Name (optional)"), text: $name)
                    .textFieldStyle(.roundedBorder).accessibilityIdentifier("scenario.new.name")
                MoneyField(label: tx("Monto de la deuda", "Debt amount"), text: $amount, identifier: "scenario.amount")
                MoneyField(label: tx("Cuota mensual (si la sabés)", "Monthly payment (if you know it)"), text: $payment, identifier: "scenario.new.payment")
                Text(tx("Sin cuota, DINCR la calcula con la tasa y el plazo.", "Without a payment, DINCR computes it from the rate and term."))
                    .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                TextField(tx("Tasa anual (%)", "Annual rate (%)"), text: $rate)
                    .keyboardType(.decimalPad).textFieldStyle(.roundedBorder).accessibilityIdentifier("scenario.new.rate")
                TextField(tx("Plazo (meses)", "Term (months)"), text: $term)
                    .keyboardType(.numberPad).textFieldStyle(.roundedBorder).accessibilityIdentifier("scenario.new.term")
            } else if choice == .consolidate {
                debtChecklist
                loanTerms
            } else {
                debtPicker
                if choice == .refinance { loanTerms }
                if choice == .extraPayment {
                    MoneyField(label: tx("¿Cuánto querés abonar?", "How much do you want to pay?"), text: $amount, identifier: "scenario.amount")
                }
            }
            if let error { Text(error).font(DincrFont.caption).foregroundStyle(DincrColor.negative) }
            Button(tx("Simular", "Simulate")) { Task { await simulate() } }
                .buttonStyle(.dincrPrimary(loading: running))
                .disabled(running || (choice == .consolidate ? chosen.count < 2 : choice != .newDebt && debtId == nil))
                .accessibilityIdentifier("scenario.run")
        }
        .dincrCard()
        .task(id: choice) { if choice != .newDebt { await loadDebts() } }
        if let result { DebtScenarioResultView(result: result) }
    }

    private var intro: String {
        switch choice {
        case .payOff: tx("Elegí una deuda: DINCR calcula cuánto te quedaría libre cada mes si la pagás completa.", "Choose a debt: DINCR shows how much you’d have left each month if you pay it off.")
        case .extraPayment: tx("Elegí una deuda y el abono: DINCR muestra qué pasa si tu banco baja la cuota o acorta el plazo.", "Choose a debt and the amount: DINCR shows what happens if your lender lowers the payment or shortens the term.")
        case .refinance: tx("Elegí una deuda y lo que te ofrecen (tasa y plazo): DINCR compara tu cuota, cuánto tardás y cuánto pagás de intereses.", "Choose a debt and the offer (rate and term): DINCR compares your payment, how long it takes and the interest.")
        case .consolidate: tx("Elegí las deudas que pagarías con un solo préstamo y lo que te ofrecen: DINCR compara hoy contra una sola cuota.", "Choose the debts one loan would pay and the offer: DINCR compares today with a single payment.")
        default: tx("Probá una deuda nueva: DINCR calcula cuánto te quedaría libre cada mes con su cuota.", "Try a new debt: DINCR shows how much you’d have left each month with its payment.")
        }
    }

    @ViewBuilder private var debtPicker: some View {
        if let debts {
            if debts.isEmpty {
                Text(tx("No tenés deudas activas registradas.", "You have no active debts recorded.")).font(DincrFont.body)
            } else {
                Picker(tx("Deuda", "Debt"), selection: $debtId) {
                    Text(tx("Elegí una deuda", "Choose a debt")).tag(Int?.none)
                    ForEach(debts) { debt in Text(debt.name ?? tx("Deuda", "Debt")).tag(Int?.some(debt.id)) }
                }
                .pickerStyle(.menu)
                .accessibilityIdentifier("scenario.debt")
            }
        } else {
            ProgressView()
        }
    }

    /// The new loan's rate, term and (optional) fee.
    @ViewBuilder private var loanTerms: some View {
        TextField(tx("Tasa anual del préstamo nuevo (%)", "New loan’s annual rate (%)"), text: $rate)
            .keyboardType(.decimalPad).textFieldStyle(.roundedBorder).accessibilityIdentifier("scenario.loan.rate")
        TextField(tx("Plazo (meses)", "Term (months)"), text: $term)
            .keyboardType(.numberPad).textFieldStyle(.roundedBorder).accessibilityIdentifier("scenario.loan.term")
        MoneyField(label: tx("Comisión o gastos (opcional)", "Fee or costs (optional)"), text: $fee, identifier: "scenario.loan.fee")
    }

    @ViewBuilder private var debtChecklist: some View {
        if let debts {
            if debts.count < 2 {
                Text(tx("Necesitás al menos dos deudas activas para juntarlas.", "You need at least two active debts to consolidate.")).font(DincrFont.body)
            } else {
                ForEach(debts) { debt in
                    Toggle(debt.name ?? tx("Deuda", "Debt"), isOn: Binding(get: { chosen.contains(debt.id) },
                                                                           set: { on in if on { chosen.insert(debt.id) } else { chosen.remove(debt.id) } }))
                        .accessibilityIdentifier("scenario.pick.\(debt.id)")
                }
            }
        } else {
            ProgressView()
        }
    }

    private func loadDebts() async {
        let epoch = model.currentEpoch
        do {
            debts = try await model.service.debts().filter { ($0.remainingAmount ?? 0) > 0 }
        } catch {
            debts = []
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos cargar tus deudas.", "We couldn’t load your debts."))
        }
    }

    private func money(_ text: String) -> Decimal? { AmountInput.parse(text, separators: model.moneyFormat.separators) }

    /// The request for the chosen what-if, or nil when an input is missing or invalid (`error` says which).
    private func request() -> DebtScenarioRequest? {
        switch choice {
        case .payOff:
            return debtId.map { .payOff(debtId: $0) }
        case .extraPayment:
            guard let debtId, let value = money(amount), value > 0 else { error = model.moneyFormat.amountHint; return nil }
            return .extraPayment(debtId: debtId, amount: value)
        case .refinance, .consolidate:
            guard let annual = money(rate), let months = Int(term.trimmingCharacters(in: .whitespaces)), months > 0 else {
                error = tx("Indicá la tasa y el plazo del préstamo nuevo.", "Enter the new loan’s rate and term."); return nil
            }
            let cost = fee.isEmpty ? nil : money(fee)
            guard fee.isEmpty || cost != nil else { error = model.moneyFormat.amountHint; return nil }
            if choice == .refinance {
                guard let debtId else { return nil }
                return .refinance(debtId: debtId, annualRate: annual, termMonths: months, fee: cost)
            }
            return .consolidate(debtIds: Array(chosen).sorted(), annualRate: annual, termMonths: months, fee: cost)
        default:
            guard let principal = money(amount), principal > 0 else { error = model.moneyFormat.amountHint; return nil }
            let cuota = payment.isEmpty ? nil : money(payment)
            let annual = rate.isEmpty ? nil : money(rate)
            let months = term.isEmpty ? nil : Int(term.trimmingCharacters(in: .whitespaces))
            guard (payment.isEmpty || cuota != nil), (rate.isEmpty || annual != nil), (term.isEmpty || months != nil) else {
                error = tx("Revisá la cuota, la tasa o el plazo.", "Check the payment, rate or term."); return nil
            }
            guard cuota != nil || (annual != nil && months != nil) else {
                error = tx("Indicá la cuota, o la tasa y el plazo.", "Enter the payment, or the rate and term."); return nil
            }
            return .newDebt(name: name.trimmingCharacters(in: .whitespaces).isEmpty ? nil : name, amount: principal,
                            monthlyPayment: cuota, annualRate: annual, termMonths: months)
        }
    }

    private func simulate() async {
        error = nil
        guard let request = request() else { return }
        running = true
        defer { running = false }
        let epoch = model.currentEpoch
        do {
            result = try await model.service.debtScenario(request)
        } catch {
            result = nil
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos simularlo.", "We couldn’t simulate it."))
        }
    }
}

/// The answer: the money left each month now and with the change; for an extra payment, both
/// lender policies side by side. Unknown figures show "—", never ₡0.
private struct DebtScenarioResultView: View {
    let result: DebtScenarioResult

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            SectionHeader(title: tx("Resultado", "Result"))
            FigureRow(label: tx("Te queda libre al mes hoy", "Left each month today"), amount: result.monthlyLeftover.current)
            if let comparison = result.comparison {
                ComparisonRows(comparison: comparison, leftover: result.monthlyLeftover)
            } else if let options = result.options {
                if let lower = options.lowerInstallment {
                    Text(tx("Si tu banco baja la cuota", "If your lender lowers the payment")).font(DincrFont.body.weight(.semibold))
                    FigureRow(label: tx("Cuota nueva", "New payment"), amount: lower.monthlyPayment)
                    FigureRow(label: tx("Te quedaría libre al mes", "Left each month"), amount: lower.monthlyLeftover)
                        .accessibilityIdentifier("scenario.result.lower")
                }
                if let shorter = options.shorterTerm {
                    Text(tx("Si tu banco acorta el plazo", "If your lender shortens the term")).font(DincrFont.body.weight(.semibold))
                    FigureRow(label: tx("Misma cuota", "Same payment"), amount: shorter.monthlyPayment)
                    InfoRow(label: tx("Terminás antes", "You finish earlier"), value: months(shorter.monthsSaved))
                    FigureRow(label: tx("Intereses que te ahorrás", "Interest you save"), amount: shorter.interestSaved)
                }
            } else {
                FigureRow(label: tx("Te quedaría libre al mes", "Left each month"), amount: result.monthlyLeftover.scenario)
                    .accessibilityIdentifier("scenario.result.leftover")
                FigureRow(label: tx("Diferencia al mes", "Monthly difference"), amount: result.monthlyLeftover.change)
            }
            if let oneTime = result.oneTimeAmount { FigureRow(label: tx("Pago único", "One-off payment"), amount: oneTime) }
            if result.oneTimeAmount != nil {
                FigureRow(label: tx("Tus ahorros después", "Your savings afterwards"), amount: result.liquidSavingsAfter)
            }
            if result.kind == "pay_off", let interest = result.payoff?.interest {
                FigureRow(label: tx("Intereses que dejás de pagar", "Interest you stop paying"), amount: interest)
            }
            if result.kind == "new_debt" {
                FigureRow(label: tx("Cuota de la deuda nueva", "New debt’s payment"), amount: result.debt?.monthlyPayment)
                if let interest = result.payoff?.interest { FigureRow(label: tx("Intereses en total", "Total interest"), amount: interest) }
            }
            if let explanation = result.explanation { Text(explanation).font(DincrFont.caption).foregroundStyle(DincrColor.text2) }
            ForEach(result.warnings ?? [], id: \.self) { Text($0).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted) }
        }
        .dincrCard()
    }

    private func months(_ value: Int?) -> String {
        guard let value else { return "—" }
        return value == 1 ? tx("1 mes", "1 month") : tx("\(value) meses", "\(value) months")
    }
}

/// Refinance / consolidate: today against the new loan, in plain rows. Unknown shows "—", never ₡0.
private struct ComparisonRows: View {
    let comparison: DebtScenarioResult.Comparison
    let leftover: DebtScenarioResult.Leftover

    var body: some View {
        FigureRow(label: tx("Cuota hoy", "Payment today"), amount: comparison.current?.monthlyPayment)
        FigureRow(label: tx("Cuota nueva", "New payment"), amount: comparison.scenario?.monthlyPayment)
            .accessibilityIdentifier("scenario.result.newPayment")
        FigureRow(label: tx("Te quedaría libre al mes", "Left each month"), amount: leftover.scenario)
        InfoRow(label: tx("Hoy terminás en", "Today you finish in"), value: months(comparison.current?.months))
        InfoRow(label: tx("Con el préstamo nuevo", "With the new loan"), value: months(comparison.scenario?.months))
        if let fee = comparison.scenario?.fee, fee > 0 { FigureRow(label: tx("Comisión", "Fee"), amount: fee) }
        if let saved = comparison.totalSaved {
            FigureRow(label: saved >= 0 ? tx("Ahorrás en intereses y costos", "You save in interest and costs")
                                        : tx("Te costaría de más", "It would cost you more"), amount: abs(saved))
                .accessibilityIdentifier("scenario.result.saved")
        } else {
            FigureRow(label: tx("Ahorro en intereses", "Interest saved"), amount: nil)
        }
    }

    private func months(_ value: Int?) -> String {
        guard let value else { return "—" }
        return value == 1 ? tx("1 mes", "1 month") : tx("\(value) meses", "\(value) months")
    }
}
