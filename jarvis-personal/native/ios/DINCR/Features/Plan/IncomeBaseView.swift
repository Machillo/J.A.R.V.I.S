import DincrCore
import DincrDesign
import SwiftUI

/// UX-7 — Plan → Ingresos y base: the declared income and essential expenses, for every plan (with
/// Metas y ahorros → Tus ahorros and Tu plan del mes → Ajustes it replaces the Situación screen;
/// same source, `financial_profiles`, and the same endpoint). An empty field is unknown and is sent
/// as null, never as zero; the observed income average is shown apart and never copied into a
/// declared value. Saving keeps the fields edited elsewhere exactly as stored.
struct IncomeBaseView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        AsyncContent(load: { try await model.service.financialSituation() }) { situation, _ in
            IncomeBaseForm(situation: situation)
        }
        .navigationTitle(tx("Ingresos y base", "Income and base"))
        .dincrScreenBackground()
    }
}

private struct IncomeBaseForm: View {
    @Environment(AppModel.self) private var model
    let situation: FinancialSituation
    @State private var incomeType = "fixed"
    @State private var salary = ""
    @State private var hourly = ""
    @State private var days = String(WorkDays.defaultValue)
    @State private var hours = ""
    @State private var frequency = "monthly"
    @State private var essentials = ""
    @State private var save = ProfileSave()
    @State private var loaded = false

    var body: some View {
        Form {
            if let observed = situation.observed?.monthlyIncomeAverage {
                Section {
                    FigureRow(label: tx("Ingreso promedio observado", "Observed average income"), amount: observed)
                } footer: {
                    Text(tx("Calculado de tus movimientos de los últimos \(situation.observed?.windowDays ?? 90) días. No reemplaza lo que declarás.", "From your transactions of the last \(situation.observed?.windowDays ?? 90) days. It doesn’t replace what you declare."))
                }
            }
            Section(tx("Ingreso", "Income")) {
                Picker(tx("Tipo de ingreso", "Income type"), selection: $incomeType) {
                    Text(tx("Salario fijo", "Fixed salary")).tag("fixed")
                    Text(tx("Por horas", "Hourly")).tag("hourly")
                }
                if incomeType == "fixed" {
                    MoneyField(label: tx("Salario mensual", "Monthly salary"), text: $salary)
                } else {
                    MoneyField(label: tx("Pago por hora", "Hourly rate"), text: $hourly)
                    TextField(tx("Horas por día", "Hours per day"), text: $hours).keyboardType(.decimalPad)
                }
                // Every income type: the backend needs it (1–7), like the historical web form.
                LabeledContent(tx("Días que trabajás por semana", "Days you work per week")) {
                    TextField(tx("Días", "Days"), text: $days)
                        .keyboardType(.numberPad)
                        .multilineTextAlignment(.trailing)
                        .frame(maxWidth: 80)
                        .accessibilityIdentifier("incomeBase.workDays")
                }
                Picker(tx("Frecuencia de pago", "Pay frequency"), selection: $frequency) {
                    Text(tx("Semanal", "Weekly")).tag("weekly")
                    Text(tx("Quincenal", "Every two weeks")).tag("biweekly")
                    Text(tx("Mensual", "Monthly")).tag("monthly")
                }
            }
            Section(tx("Gastos esenciales", "Essential expenses")) {
                MoneyField(label: tx("Gastos esenciales del mes", "Essential monthly expenses"), text: $essentials)
            }
            ProfileSaveSection(save: save, id: "incomeBase.save") { Task { await submit() } }
        }
        .scrollContentBackground(.hidden)
        .onAppear(perform: prefill)
    }

    private func prefill() {
        guard !loaded else { return }
        loaded = true
        let format = model.moneyFormat
        let profile = situation.financialProfile
        incomeType = profile?.incomeType ?? "fixed"
        salary = profile?.fixedMonthlySalary.map(format.inputText) ?? ""
        hourly = profile?.hourlyRate.map(format.inputText) ?? ""
        days = String(profile?.workDaysPerWeek ?? WorkDays.defaultValue)
        hours = profile?.hoursPerDay.map { "\($0)" } ?? ""
        frequency = profile?.payFrequency ?? "monthly"
        essentials = profile?.essentialMonthlyExpenses.map(format.inputText) ?? ""
    }

    private func submit() async {
        let separators = model.moneyFormat.separators
        guard let salaryValue = ProfileSave.optional(salary, separators), let hourlyValue = ProfileSave.optional(hourly, separators),
              let essentialsValue = ProfileSave.optional(essentials, separators) else {
            save.error = model.moneyFormat.amountHint; return
        }
        guard let workDays = WorkDays.parse(days) else {
            save.error = tx("Indicá cuántos días trabajás por semana, de 1 a 7.", "Enter how many days you work per week, from 1 to 7."); return
        }
        var profile = situation.financialProfile ?? FinancialProfile()
        profile.incomeType = incomeType
        profile.fixedMonthlySalary = incomeType == "fixed" ? salaryValue : nil
        profile.hourlyRate = incomeType == "hourly" ? hourlyValue : nil
        profile.workDaysPerWeek = workDays
        profile.hoursPerDay = incomeType == "hourly" ? Decimal(string: hours.replacingOccurrences(of: ",", with: "."), locale: Locale(identifier: "en_US_POSIX")) : nil
        profile.payFrequency = frequency
        profile.essentialMonthlyExpenses = essentialsValue
        await save.run(profile, model: model)
    }
}

/// UX-7 — Tu plan del mes → Ajustes (VIP): the plan priority and the personal minimum per month,
/// moved from the Situación screen. Same source and endpoint; every other declared field is sent
/// back exactly as stored. "No preference" stays null (nothing the user did not choose is stored).
struct PlanPreferencesView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        AsyncContent(load: { try await model.service.financialSituation() }) { situation, _ in
            PlanPreferencesForm(situation: situation)
        }
        .navigationTitle(tx("Ajustes del plan", "Plan settings"))
        .dincrScreenBackground()
    }
}

private struct PlanPreferencesForm: View {
    @Environment(AppModel.self) private var model
    let situation: FinancialSituation
    @State private var preference = ""
    @State private var minimum = ""
    @State private var save = ProfileSave()
    @State private var loaded = false

    /// The backend saves the whole declared profile, which needs a declared income: until there is
    /// one, the settings say where to declare it (the old Situación form asked for it on the same page).
    private var incomeDeclared: Bool { ProfileSave.incomeDeclared(situation.financialProfile) }

    var body: some View {
        Form {
            if !incomeDeclared {
                Section {
                    Text(tx("Primero declará tu ingreso: tus ajustes se guardan junto con él.", "Declare your income first: your settings are saved with it."))
                        .foregroundStyle(DincrColor.text2)
                    NavigationLink { IncomeBaseView() } label: { Text(tx("Completar ingresos y base", "Complete income and base")) }
                        .accessibilityIdentifier("planPreferences.declareIncome")
                }
            }
            Section {
                Picker(tx("Prioridad", "Priority"), selection: $preference) {
                    ForEach(StrategyPreference.choices, id: \.self) { choice in
                        Text(Self.label(choice)).tag(choice?.rawValue ?? "")
                    }
                }
                .accessibilityIdentifier("planPreferences.priority")
                MoneyField(label: tx("Mínimo personal por mes", "Personal minimum per month"), text: $minimum)
            } footer: {
                Text(tx("Dejá vacío el mínimo si no lo sabés: DINCR lo trata como desconocido, no como cero.", "Leave the minimum empty if you don’t know it: DINCR treats it as unknown, not zero."))
            }
            if incomeDeclared {
                ProfileSaveSection(save: save, id: "planPreferences.save") { Task { await submit() } }
            }
        }
        .scrollContentBackground(.hidden)
        .onAppear {
            guard !loaded else { return }
            loaded = true
            preference = situation.financialProfile?.strategyPreference ?? ""
            minimum = situation.financialProfile?.discretionaryMonthlyMinimum.map(model.moneyFormat.inputText) ?? ""
        }
    }

    static func label(_ choice: StrategyPreference?) -> String {
        switch choice {
        case nil: tx("Sin preferencia", "No preference")
        case .debt: tx("Salir de deudas", "Get out of debt")
        case .emergency: tx("Fondo de emergencia", "Emergency fund")
        case .goals: tx("Metas", "Goals")
        case .balanced: tx("Equilibrado", "Balanced")
        }
    }

    private func submit() async {
        guard let minimumValue = ProfileSave.optional(minimum, model.moneyFormat.separators) else {
            save.error = model.moneyFormat.amountHint; return
        }
        var profile = ProfileSave.withDefaults(situation.financialProfile)
        profile.strategyPreference = preference.isEmpty ? nil : preference
        profile.discretionaryMonthlyMinimum = minimumValue
        await save.run(profile, model: model)
    }
}

/// UX-7 — Metas y ahorros → Tus ahorros: the declared available savings and the emergency-fund
/// target, for every plan (moved from the Situación screen; the same `financial_profiles` fields and
/// endpoint, the same figures Salvavidas reads). Saving needs a declared income, as before.
struct DeclaredSavingsView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        AsyncContent(load: { try await model.service.financialSituation() }) { situation, _ in
            DeclaredSavingsForm(situation: situation)
        }
        .navigationTitle(tx("Tus ahorros", "Your savings"))
        .dincrScreenBackground()
    }
}

private struct DeclaredSavingsForm: View {
    @Environment(AppModel.self) private var model
    let situation: FinancialSituation
    @State private var savings = ""
    @State private var emergency = ""
    @State private var save = ProfileSave()
    @State private var loaded = false

    private var incomeDeclared: Bool { ProfileSave.incomeDeclared(situation.financialProfile) }

    var body: some View {
        Form {
            if !incomeDeclared {
                Section {
                    Text(tx("Primero declará tu ingreso: tus ahorros se guardan junto con él.", "Declare your income first: your savings are saved with it."))
                        .foregroundStyle(DincrColor.text2)
                    NavigationLink { IncomeBaseView() } label: { Text(tx("Completar ingresos y base", "Complete income and base")) }
                        .accessibilityIdentifier("declaredSavings.declareIncome")
                }
            }
            Section {
                MoneyField(label: tx("Ahorros disponibles", "Available savings"), text: $savings)
                MoneyField(label: tx("Meta de fondo de emergencia", "Emergency fund target"), text: $emergency)
            }
            if incomeDeclared {
                ProfileSaveSection(save: save, id: "declaredSavings.save") { Task { await submit() } }
            }
        }
        .scrollContentBackground(.hidden)
        .onAppear {
            guard !loaded else { return }
            loaded = true
            let format = model.moneyFormat
            savings = situation.financialProfile?.liquidSavings.map(format.inputText) ?? ""
            emergency = situation.financialProfile?.emergencyFundTarget.map(format.inputText) ?? ""
        }
    }

    private func submit() async {
        let separators = model.moneyFormat.separators
        guard let savingsValue = ProfileSave.optional(savings, separators), let emergencyValue = ProfileSave.optional(emergency, separators) else {
            save.error = model.moneyFormat.amountHint; return
        }
        var profile = ProfileSave.withDefaults(situation.financialProfile)
        profile.liquidSavings = savingsValue
        profile.emergencyFundTarget = emergencyValue
        await save.run(profile, model: model)
    }
}

/// Saving one part of the declared financial profile (`PUT /user-product/financial-situation`).
@MainActor @Observable
private final class ProfileSave {
    var error: String?
    var saved = false
    var saving = false

    /// Whether the stored profile has the income the backend requires to save it.
    nonisolated static func incomeDeclared(_ profile: FinancialProfile?) -> Bool {
        guard let profile else { return false }
        switch profile.incomeType {
        case "fixed": return profile.fixedMonthlySalary != nil
        case "hourly": return profile.hourlyRate != nil && profile.hoursPerDay != nil
        default: return false
        }
    }

    /// The stored profile with the same defaults the old Situación form sent for what was never stored.
    nonisolated static func withDefaults(_ stored: FinancialProfile?) -> FinancialProfile {
        var profile = stored ?? FinancialProfile()
        profile.workDaysPerWeek = profile.workDaysPerWeek ?? WorkDays.defaultValue
        profile.payFrequency = profile.payFrequency ?? "monthly"
        return profile
    }

    /// Empty → nil (unknown); anything else must parse, or nothing is sent.
    nonisolated static func optional(_ text: String, _ separators: MoneyFormat.Separators) -> Decimal?? {
        if text.trimmingCharacters(in: .whitespaces).isEmpty { return .some(nil) }
        guard let value = AmountInput.parseZeroOrMore(text, separators: separators) else { return nil }
        return .some(value)
    }

    func run(_ profile: FinancialProfile, model: AppModel) async {
        saving = true; error = nil; saved = false
        defer { saving = false }
        let epoch = model.currentEpoch
        do {
            _ = try await model.service.updateFinancialSituation(profile, idempotencyKey: IdempotencyKey.new())
            saved = true
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardar.", "We couldn’t save."))
        }
    }
}

private struct ProfileSaveSection: View {
    @Environment(AppModel.self) private var model
    let save: ProfileSave
    let id: String
    let action: () -> Void

    var body: some View {
        Section {
            if let error = save.error { Text(error).foregroundStyle(DincrColor.negative) }
            if save.saved { Label(tx("Guardado", "Saved"), systemImage: "checkmark.circle").foregroundStyle(DincrColor.positive) }
            Button(tx("Guardar", "Save"), action: action).disabled(save.saving || !model.flags.isEnabled(.financialWrites))
                .accessibilityIdentifier(id)
        } footer: {
            Text(tx("Dejá vacío lo que no sabés: DINCR lo trata como desconocido, no como cero.", "Leave empty what you don’t know: DINCR treats it as unknown, not zero."))
        }
    }
}
