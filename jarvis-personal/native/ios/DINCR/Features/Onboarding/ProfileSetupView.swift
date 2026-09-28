import DincrCore
import DincrDesign
import SwiftUI

/// PARITY A9 — four steps (name → goal → money format → institutions), saved once at the end.
/// Currencies follow the CRC/USD scope being set for onboarding (Agent B, PR #265).
struct ProfileSetupView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var step = 0
    @State private var name = ""
    @State private var goal = ""
    @State private var baseCurrency = "CRC"
    @State private var alsoOtherCurrency = false
    @State private var separators: MoneyFormat.Separators = .dotComma
    @State private var placement: MoneyFormat.Placement = .before
    @State private var institutions: Set<String> = []
    @State private var saving = false
    @State private var error: String?

    private let totalSteps = 4

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: DincrSpacing.s6) {
                    ProgressView(value: Double(step + 1), total: Double(totalSteps))
                        .tint(DincrColor.tint)
                        .accessibilityLabel(tx("Paso \(step + 1) de \(totalSteps)", "Step \(step + 1) of \(totalSteps)"))
                    Group {
                        switch step {
                        case 0: nameStep
                        case 1: goalStep
                        case 2: moneyStep
                        default: institutionsStep
                        }
                    }
                    .transition(.opacity)
                    if let error { ErrorStateView(message: error) }
                }
                .padding(DincrSpacing.s4)
                .frame(maxWidth: 600)
                .frame(maxWidth: .infinity)
            }
            .scrollDismissesKeyboard(.interactively)
            .dincrScreenBackground()
            .safeAreaInset(edge: .bottom) { footer }
            .navigationTitle(tx("Tu perfil", "Your profile"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                if step > 0 {
                    ToolbarItem(placement: .topBarLeading) {
                        Button { withAnimation(DincrMotion.quick(reduceMotion)) { step -= 1 } } label: {
                            Label(tx("Atrás", "Back"), systemImage: "chevron.backward")
                        }
                        .disabled(saving)
                    }
                }
            }
        }
        .onAppear {
            if name.isEmpty { name = model.profile?.firstName ?? "" }
        }
        .sensoryFeedback(.error, trigger: error)
    }

    private var canContinue: Bool {
        switch step {
        case 0: !name.trimmingCharacters(in: .whitespaces).isEmpty
        case 1: !goal.isEmpty
        default: true
        }
    }

    private var footer: some View {
        VStack(spacing: DincrSpacing.s2) {
            Button(step == totalSteps - 1 ? tx("Entrar a DINCR", "Enter DINCR") : tx("Continuar", "Continue")) {
                if step == totalSteps - 1 { Task { await finish() } }
                else { withAnimation(DincrMotion.quick(reduceMotion)) { step += 1 } }
            }
            .buttonStyle(.dincrPrimary(loading: saving))
            .disabled(!canContinue || saving)
            .accessibilityIdentifier("setup.continue")
            Text(step == totalSteps - 1
                 ? tx("Estas preferencias quedarán guardadas en tu cuenta.", "These preferences will be saved to your account.")
                 : tx("Guardamos todo al terminar los cuatro pasos.", "We save everything when you finish the four steps."))
                .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
        }
        .padding(.horizontal, DincrSpacing.s4)
        .padding(.vertical, DincrSpacing.s3)
        .frame(maxWidth: 600)
        .frame(maxWidth: .infinity)
        .background(.bar)
    }

    private func header(_ title: String, _ detail: String) -> some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Text(title).font(DincrFont.title1).foregroundStyle(DincrColor.text).accessibilityAddTraits(.isHeader)
            Text(detail).font(DincrFont.body).foregroundStyle(DincrColor.text2)
        }
    }

    private var nameStep: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s4) {
            header(tx("¿Cómo querés que te llamemos?", "What should we call you?"), tx("Podés cambiarlo después.", "You can change it later."))
            DincrTextField(label: tx("Tu nombre", "Your name"), text: $name, prompt: tx("Ejemplo: Ana", "Example: Ana"))
                .textContentType(.givenName)
                .submitLabel(.next)
                .onSubmit { if canContinue { step += 1 } }
        }
    }

    private var goalStep: some View {
        let goals: [(String, String, String)] = [
            ("debt", "creditcard", tx("Salir de deudas", "Pay off debt")),
            ("save", "banknote", tx("Ahorrar para algo importante", "Save for something important")),
            ("partner", "person.2", tx("Organizar dinero en pareja o familia", "Manage money with a partner or family")),
            ("life_change", "sparkles", tx("Prepararme para un cambio importante", "Prepare for a big change")),
            ("control", "target", tx("Tomar control de mis finanzas", "Take control of my finances")),
            ("explore", "questionmark.circle", tx("Todavía no estoy seguro", "I’m not sure yet")),
        ]
        return VStack(alignment: .leading, spacing: DincrSpacing.s4) {
            header(tx("¿Qué querés lograr primero?", "What do you want to achieve first?"), tx("Nos ayuda a mostrarte primero lo que más te sirve.", "It helps us show you what matters most first."))
            VStack(spacing: 0) {
                ForEach(goals, id: \.0) { id, symbol, label in
                    Button { goal = id } label: {
                        HStack(spacing: DincrSpacing.s3) {
                            Image(systemName: symbol).frame(width: 28).foregroundStyle(DincrColor.tint)
                            Text(label).font(DincrFont.body).foregroundStyle(DincrColor.text).multilineTextAlignment(.leading)
                            Spacer()
                            Image(systemName: goal == id ? "checkmark.circle.fill" : "circle")
                                .foregroundStyle(goal == id ? DincrColor.tint : DincrColor.fieldBorder)
                        }
                        .padding(.vertical, DincrSpacing.s3)
                        .frame(minHeight: 52)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityAddTraits(goal == id ? [.isSelected] : [])
                    if id != goals.last?.0 { Divider().overlay(DincrColor.line) }
                }
            }
            .padding(.horizontal, DincrSpacing.s4)
            .background(DincrColor.surface, in: RoundedRectangle(cornerRadius: DincrRadius.lg, style: .continuous))
            .sensoryFeedback(.selection, trigger: goal)
        }
    }

    private var moneyStep: some View {
        let preview = MoneyFormat(currency: baseCurrency, separators: separators, placement: placement)
        return VStack(alignment: .leading, spacing: DincrSpacing.s4) {
            header(tx("¿Cómo querés ver tu dinero?", "How do you want to see your money?"), tx("No convertimos montos sin avisarte.", "We never convert amounts without telling you."))
            VStack(alignment: .leading, spacing: DincrSpacing.s4) {
                LabeledContent(tx("Moneda principal", "Main currency")) {
                    Picker(tx("Moneda principal", "Main currency"), selection: $baseCurrency) {
                        Text(tx("CRC · Colón", "CRC · Colón")).tag("CRC")
                        Text(tx("USD · Dólar", "USD · Dollar")).tag("USD")
                    }
                    .pickerStyle(.menu)
                }
                Toggle(isOn: $alsoOtherCurrency) {
                    Text(tx("También uso \(baseCurrency == "CRC" ? "USD" : "CRC")", "I also use \(baseCurrency == "CRC" ? "USD" : "CRC")"))
                }
                .tint(DincrColor.tint)
                VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                    Text(tx("Formato de números", "Number format")).font(DincrFont.label).foregroundStyle(DincrColor.text2)
                    Picker(tx("Formato de números", "Number format"), selection: $separators) {
                        Text("123.456,78").tag(MoneyFormat.Separators.dotComma)
                        Text("123,456.78").tag(MoneyFormat.Separators.commaDot)
                    }
                    .pickerStyle(.segmented)
                }
                VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                    Text(tx("Posición del símbolo", "Symbol position")).font(DincrFont.label).foregroundStyle(DincrColor.text2)
                    Picker(tx("Posición del símbolo", "Symbol position"), selection: $placement) {
                        Text(tx("Antes", "Before")).tag(MoneyFormat.Placement.before)
                        Text(tx("Después", "After")).tag(MoneyFormat.Placement.after)
                    }
                    .pickerStyle(.segmented)
                }
                HStack {
                    Text(tx("Así se verá", "Preview")).font(DincrFont.label).foregroundStyle(DincrColor.textMuted)
                    Spacer()
                    Text(preview.string(123_456.78)).font(DincrFont.title2.monospacedDigit()).foregroundStyle(DincrColor.text)
                }
                .accessibilityElement(children: .combine)
            }
            .dincrCard()
            .sensoryFeedback(.selection, trigger: separators)
        }
    }

    private var institutionsStep: some View {
        let banks: [(String, String, Bool)] = [
            ("bac", "BAC Credomatic", true), ("bn", "Banco Nacional", false), ("bcr", "Banco de Costa Rica", false),
            ("popular", "Banco Popular", false), ("davivienda", "Davivienda", false),
            ("scotiabank", tx("DAVIbank (antes Scotiabank)", "DAVIbank (formerly Scotiabank)"), false),
            ("promerica", "Promerica", false), ("multimoney", "MultiMoney", true),
        ]
        return VStack(alignment: .leading, spacing: DincrSpacing.s4) {
            header(tx("¿Qué bancos usás?", "Which banks do you use?"), tx("Esto no conecta ninguna cuenta ni comparte contraseñas. DINCR nunca te pedirá la contraseña de tu banco.", "This doesn’t connect any account or share passwords. DINCR will never ask for your bank password."))
            VStack(spacing: 0) {
                ForEach(banks, id: \.0) { id, name, supported in
                    Toggle(isOn: Binding(get: { institutions.contains(id) }, set: { on in
                        if on { institutions.insert(id) } else { institutions.remove(id) }
                    })) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(name).font(DincrFont.body).foregroundStyle(DincrColor.text)
                            if supported {
                                Text(tx("Compatible con correos financieros en VIP", "Works with financial emails in VIP"))
                                    .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                            }
                        }
                    }
                    .tint(DincrColor.tint)
                    .padding(.vertical, DincrSpacing.s2)
                    .frame(minHeight: 52)
                    if id != banks.last?.0 { Divider().overlay(DincrColor.line) }
                }
            }
            .padding(.horizontal, DincrSpacing.s4)
            .background(DincrColor.surface, in: RoundedRectangle(cornerRadius: DincrRadius.lg, style: .continuous))
        }
    }

    private func finish() async {
        guard !saving else { return } // one submit, however fast the taps
        saving = true
        error = nil
        defer { saving = false }
        var currencies = [baseCurrency]
        if alsoOtherCurrency { currencies.append(baseCurrency == "CRC" ? "USD" : "CRC") }
        let setup = ProfileSetup(
            displayName: name.trimmingCharacters(in: .whitespaces), usageGoal: goal, baseCurrency: baseCurrency,
            enabledCurrencies: currencies, numberFormat: separators.rawValue, currencyPlacement: placement.rawValue,
            selectedFinancialInstitutions: institutions.sorted()
        )
        do {
            model.apply(try await model.service.completeProfileSetup(setup))
        } catch let apiError as APIError {
            error = apiError.message
        } catch is CancellationError {
            return
        } catch AuthError.signedOut {
            await model.signOut()
        } catch {
            self.error = tx("No pudimos guardar tus preferencias. Intentá nuevamente.", "We couldn’t save your preferences. Please try again.")
        }
    }
}

/// Labeled text field with a visible label above and a ≥3:1 boundary (DESIGN.md → Inputs).
struct DincrTextField: View {
    let label: String
    @Binding var text: String
    var prompt: String = ""
    var error: String? = nil
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Text(label).font(DincrFont.label).foregroundStyle(DincrColor.text2)
            TextField(label, text: $text, prompt: Text(prompt).foregroundStyle(DincrColor.textMuted))
                .font(DincrFont.body)
                .foregroundStyle(DincrColor.text)
                .focused($focused)
                .padding(.horizontal, DincrSpacing.s4)
                .frame(minHeight: 52)
                .background(DincrColor.surface, in: RoundedRectangle(cornerRadius: DincrRadius.sm, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: DincrRadius.sm, style: .continuous)
                        .strokeBorder(error != nil ? DincrColor.negative : (focused ? DincrColor.tint : DincrColor.fieldBorder), lineWidth: focused || error != nil ? 2 : 1)
                )
            if let error {
                Label(error, systemImage: "exclamationmark.circle")
                    .font(DincrFont.caption)
                    .foregroundStyle(DincrColor.negative)
            }
        }
    }
}
