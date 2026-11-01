import DincrCore
import DincrDesign
import SwiftUI

/// RT-1 — Plan → Retiro (VIP and the Owner): what you have put aside for retirement (ROP and a voluntary
/// pension, declared here), read in simple words (`RetirementReading`): how much, the years left, and
/// a common age reference against your normal month's income. Saving is your explicit action.
/// Android twin: `RetirementScreen.kt`.
struct RetirementView: View {
    @Environment(AppModel.self) private var model
    @State private var generation = 0

    struct Loaded: Equatable {
        let retirement: Retirement
        let monthlyIncome: Decimal?
    }

    var body: some View {
        ScreenScroll(title: tx("Retiro", "Retirement")) {
            AsyncContent(load: { () async throws -> Loaded in
                async let retirement = model.service.retirement()
                // Optional: without a normal month there is no age comparison.
                let income = (try? await model.service.financialAnalysis()).flatMap(FinancialReading.normal)?.income
                return Loaded(retirement: try await retirement, monthlyIncome: income)
            }) { loaded, _ in
                RetirementContent(loaded: loaded) { generation += 1 }
            }
            .id(generation)
            FinancialDisclaimer()
        }
    }
}

private struct RetirementContent: View {
    @Environment(AppModel.self) private var model
    let loaded: RetirementView.Loaded
    let saved: () -> Void
    @State private var rop = ""
    @State private var voluntary = ""
    @State private var birth = ""
    @State private var age = ""
    @State private var error: String?
    @State private var saving = false

    var body: some View {
        let year = Calendar(identifier: .gregorian).component(.year, from: Date())
        let lines = RetirementReading.lines(loaded.retirement.config, monthlyIncome: loaded.monthlyIncome, year: year, format: model.moneyFormat)
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            if lines.isEmpty {
                Text(tx("Todavía no registraste tu ahorro para el retiro.", "You haven’t recorded your retirement savings yet.")).font(DincrFont.body)
            }
            ForEach(Array(lines.enumerated()), id: \.offset) { index, line in
                Text(line).font(index == 0 ? DincrFont.title2 : DincrFont.bodySmall)
                    .foregroundStyle(index == 0 ? DincrColor.text : DincrColor.text2).fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .dincrCard()
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("retirement.reading")
        VStack(alignment: .leading, spacing: DincrSpacing.s3) {
            SectionHeader(title: tx("Tus datos", "Your details"))
            MoneyField(label: tx("Saldo del ROP", "ROP balance"), text: $rop, identifier: "retirement.rop")
            MoneyField(label: tx("Pensión voluntaria (si tenés)", "Voluntary pension (if any)"), text: $voluntary, identifier: "retirement.voluntary")
            TextField(tx("Año de nacimiento", "Year of birth"), text: $birth).keyboardType(.numberPad).textFieldStyle(.roundedBorder)
                .accessibilityIdentifier("retirement.birth")
            TextField(tx("Edad de retiro (65 si no sabés)", "Retirement age (65 if unsure)"), text: $age).keyboardType(.numberPad).textFieldStyle(.roundedBorder)
                .accessibilityIdentifier("retirement.age")
            Text(tx("El saldo del ROP aparece en el estado de cuenta de tu operadora de pensiones.", "Your ROP balance is on your pension fund statement."))
                .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            if let error { Text(error).font(DincrFont.caption).foregroundStyle(DincrColor.negative) }
            Button(tx("Guardar", "Save")) { Task { await save() } }
                .buttonStyle(.dincrPrimary(loading: saving)).disabled(saving)
                .accessibilityIdentifier("retirement.save")
        }
        .dincrCard()
        .onAppear(perform: prefill)
    }

    private func prefill() {
        let config = loaded.retirement.config
        rop = config.ropBalance.map(model.moneyFormat.inputText) ?? ""
        voluntary = config.voluntaryBalance.map(model.moneyFormat.inputText) ?? ""
        birth = config.birthYear.map(String.init) ?? ""
        age = config.retireAge.map(String.init) ?? ""
    }

    private func save() async {
        let separators = model.moneyFormat.separators
        let ropValue = rop.isEmpty ? nil : CorrectionInput.amount(rop, separators: separators)
        let voluntaryValue = voluntary.isEmpty ? nil : CorrectionInput.amount(voluntary, separators: separators)
        let birthValue = birth.isEmpty ? nil : Int(birth.trimmingCharacters(in: .whitespaces))
        let ageValue = age.isEmpty ? nil : Int(age.trimmingCharacters(in: .whitespaces))
        guard (rop.isEmpty || ropValue != nil), (voluntary.isEmpty || voluntaryValue != nil),
              (birth.isEmpty || birthValue != nil), (age.isEmpty || ageValue != nil) else {
            error = tx("Revisá los montos, el año y la edad.", "Check the amounts, the year and the age."); return
        }
        saving = true; error = nil
        defer { saving = false }
        let epoch = model.currentEpoch
        do {
            _ = try await model.service.updateRetirement(RetirementUpdate(ropBalance: ropValue, voluntaryBalance: voluntaryValue, birthYear: birthValue, retireAge: ageValue))
            saved()
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardar.", "We couldn’t save."))
        }
    }
}
