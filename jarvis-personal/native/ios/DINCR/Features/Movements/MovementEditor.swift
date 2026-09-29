import DincrCore
import DincrDesign
import SwiftUI

/// PARITY D3 (add income/expense), D4/D5 (edit). Sheet with Cancel/Save, visible labels,
/// inline errors plus a summary when more than one field fails, single-flight save.
/// An edit sends back exactly what is stored unless the user changes it: the amount is prefilled
/// unrounded and the stored category stays selectable, so saving a new description never
/// rewrites the amount or the category.
struct MovementEditor: View {
    enum Mode: Identifiable {
        case create
        case edit(Movement)
        var id: String {
            switch self {
            case .create: "create"
            case .edit(let movement): movement.movementId
            }
        }
    }

    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @Environment(\.moneyFormat) private var format
    let mode: Mode
    /// The user's own most recent rate (never a market rate), to prefill a foreign-currency entry.
    var latestRate: Decimal? = nil
    let onSaved: (String) -> Void

    @State private var kind: Movement.Kind = .expense
    @State private var amountText = ""
    @State private var prefilledAmountText = ""
    /// The currency the amount is typed in (#269): the base, or another entry currency with the user's rate.
    @State private var currency = ""
    @State private var rateText = ""
    @State private var prefilledRateText = ""
    @State private var storedCategory: String?
    /// One key per distinct submission: a retry of the same body reuses it, so the backend
    /// answers from the first request instead of creating a second movement.
    @State private var submission: (body: EntryCreate, key: String)?
    @State private var description = ""
    @State private var category = ""
    @State private var date = Date.now
    @State private var saving = false
    @State private var fieldErrors: [Field: String] = [:]
    @State private var saveError: String?
    @State private var saved = 0
    @AccessibilityFocusState private var summaryFocused: Bool

    enum Field: Hashable { case amount, description, rate }

    private var base: String { (model.profile?.baseCurrency ?? "CRC").uppercased() }
    private var isForeign: Bool { !currency.isEmpty && currency != base }
    /// Currencies offered: only when the backend converts them, and only for rows that accept one.
    private var currencies: [String] {
        let typing = model.profile?.typingCurrencies ?? [base]
        if case .edit(let movement) = mode, !movement.acceptsCurrency { return [base] }
        return typing
    }

    private static let expenseCategories = ["Comida", "Vivienda", "Servicios", "Internet", "Teléfono", "Transporte", "Gasolina", "Restaurante", "Salud", "Entretenimiento", "Compras", "Seguros", "Deporte", "Mascotas", "Otros"]
    private static let incomeCategories = ["Salario", "Boleta de pago", "Bono", "Reembolso", "Otros ingresos"]

    private var isEditing: Bool { if case .edit = mode { true } else { false } }

    var body: some View {
        NavigationStack {
            Form {
                if fieldErrors.count > 1 {
                    Section {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(tx("Revisá \(fieldErrors.count) campos", "Check \(fieldErrors.count) fields")).font(DincrFont.title2)
                            ForEach(Array(fieldErrors.values.sorted()), id: \.self) { Text("• \($0)").font(DincrFont.bodySmall) }
                        }
                        .foregroundStyle(DincrColor.negative)
                        .accessibilityElement(children: .combine)
                        .accessibilityFocused($summaryFocused)
                    }
                }
                if !isEditing {
                    Section {
                        Picker(tx("Tipo", "Type"), selection: $kind) {
                            Text(tx("Gasto", "Expense")).tag(Movement.Kind.expense)
                            Text(tx("Ingreso", "Income")).tag(Movement.Kind.income)
                        }
                        .pickerStyle(.segmented)
                        .listRowBackground(Color.clear)
                        .listRowInsets(EdgeInsets())
                    }
                }
                Section {
                    if currencies.count > 1 {
                        Picker(tx("Moneda", "Currency"), selection: $currency) {
                            ForEach(currencies, id: \.self) { Text($0).tag($0) }
                        }
                        .pickerStyle(.segmented)
                        .accessibilityIdentifier("editor.currency")
                    }
                    VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                        Text(tx("Monto", "Amount")).font(DincrFont.label).foregroundStyle(DincrColor.text2)
                        HStack(spacing: DincrSpacing.s2) {
                            Text(MoneyFormat(currency: currency.isEmpty ? base : currency).symbol).font(DincrFont.title1).foregroundStyle(DincrColor.textMuted).accessibilityHidden(true)
                            TextField(tx("Monto", "Amount"), text: $amountText, prompt: Text("0"))
                                .font(DincrFont.title1.monospacedDigit())
                                .keyboardType(.decimalPad)
                                .accessibilityIdentifier("editor.amount")
                        }
                        if let error = fieldErrors[.amount] { fieldError(error) }
                    }
                    if isForeign {
                        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                            Text(tx("Tipo de cambio (colones por 1 dólar)", "Exchange rate (colones per 1 dollar)")).font(DincrFont.label).foregroundStyle(DincrColor.text2)
                            TextField(tx("Tipo de cambio", "Exchange rate"), text: $rateText, prompt: Text(format.inputText(Decimal(string: "507.5")!)))
                                .keyboardType(.decimalPad)
                                .accessibilityIdentifier("editor.rate")
                            if let error = fieldErrors[.rate] { fieldError(error) }
                            if let preview = ConversionPreview.baseAmount(typed: AmountInput.parse(amountText, separators: format.separators), currency: currency, base: base,
                                                                          rate: RateInput.parse(rateText, separators: format.separators)) {
                                Text(tx("Se guardará como \(format.string(preview)). DINCR usa tu tipo de cambio; no consulta tasas.", "Saved as \(format.string(preview)). DINCR uses your rate; it doesn’t look rates up."))
                                    .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                                    .accessibilityIdentifier("editor.preview")
                            }
                        }
                    }
                    VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                        Text(tx("Descripción", "Description")).font(DincrFont.label).foregroundStyle(DincrColor.text2)
                        TextField(tx("Descripción", "Description"), text: $description, prompt: Text(tx("¿Qué movimiento fue?", "What was it?")))
                            .accessibilityIdentifier("editor.description")
                        if let error = fieldErrors[.description] { fieldError(error) }
                    }
                }
                Section {
                    Picker(tx("Categoría", "Category"), selection: $category) {
                        ForEach(categories, id: \.self) { Text($0).tag($0) }
                    }
                    DatePicker(tx("Fecha", "Date"), selection: $date, in: ...Date.now.addingTimeInterval(86_400 * 365), displayedComponents: .date)
                }
                if kind == .income && !isEditing {
                    Section {
                        Text(tx("Ingresá el monto real que recibiste según tu boleta o depósito.", "Enter the actual amount you received, per your pay stub or deposit."))
                            .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                    }
                }
                if let saveError {
                    Section { ErrorStateView(message: saveError).listRowInsets(EdgeInsets()) }
                        .listRowBackground(Color.clear)
                }
            }
            .scrollContentBackground(.hidden)
            .dincrScreenBackground()
            .navigationTitle(isEditing ? tx("Editar movimiento", "Edit transaction") : tx("Nuevo movimiento", "New transaction"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(tx("Cancelar", "Cancel")) { dismiss() }.disabled(saving)
                }
                ToolbarItem(placement: .confirmationAction) {
                    if saving { ProgressView() } else {
                        Button(tx("Guardar", "Save")) { Task { await save() } }
                            .fontWeight(.semibold)
                            .accessibilityIdentifier("editor.save")
                    }
                }
                ToolbarItemGroup(placement: .keyboard) {
                    Spacer()
                    Button(tx("Listo", "Done")) { UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil) }
                }
            }
            .interactiveDismissDisabled(saving || hasChanges)
            .onChange(of: kind) { _, _ in if !categories.contains(category) { category = categories[0] } }
            .onChange(of: currency) { oldValue, newValue in
                // Switching currency on an edit never reinterprets the typed number (US$10 is not ₡10):
                // the amount is asked again, and the untouched stored values no longer apply.
                if isEditing, !oldValue.isEmpty {
                    amountText = ""
                    rateText = ""
                    prefilledRateText = "\u{0}"
                }
                // A foreign entry starts from the user's own latest rate (editable), never a market rate.
                if newValue != base, rateText.isEmpty, let latestRate { rateText = format.inputText(latestRate) }
            }
            .onAppear(perform: prefill)
            .sensoryFeedback(.success, trigger: saved)
            .sensoryFeedback(.error, trigger: saveError)
        }
        .presentationDetents([.large])
    }

    private var categories: [String] {
        let base = kind == .income ? Self.incomeCategories : Self.expenseCategories
        guard let storedCategory, !base.contains(storedCategory) else { return base }
        return [storedCategory] + base
    }

    private var hasChanges: Bool {
        guard case .edit(let movement) = mode else { return !amountText.isEmpty || !description.isEmpty }
        return description != (movement.description ?? "") || AmountInput.parse(amountText, separators: format.separators) != movement.amount
    }

    private func fieldError(_ message: String) -> some View {
        Label(message, systemImage: "exclamationmark.circle").font(DincrFont.caption).foregroundStyle(DincrColor.negative)
    }

    private func prefill() {
        guard case .edit(let movement) = mode else {
            if category.isEmpty { category = categories[0] }
            if currency.isEmpty { currency = base }
            return
        }
        kind = movement.transactionType
        if movement.isCurrencyEditable(entryCurrencies: model.profile?.entryCurrencies ?? []),
           let original = movement.originalAmount, let code = movement.originalCurrency, let rate = movement.exchangeRate {
            // A row typed in another currency is edited in that currency, with its stored rate.
            currency = code.uppercased()
            amountText = format.inputText(original)
            rateText = format.inputText(rate)
        } else {
            currency = base
            amountText = format.inputText(movement.amount)
        }
        prefilledAmountText = amountText
        prefilledRateText = rateText
        description = movement.description ?? ""
        storedCategory = movement.category.flatMap { $0.isEmpty ? nil : $0 }
        category = storedCategory ?? categories[0]
        if let day = movement.day, let parsed = Self.dayFormatter.date(from: day) { date = parsed }
    }

    private func validate() -> (amount: Decimal, rate: Decimal?)? {
        var errors: [Field: String] = [:]
        let amount: Decimal?
        let storedForeign: Bool = {
            if case .edit(let movement) = mode { return movement.isCurrencyEditable(entryCurrencies: model.profile?.entryCurrencies ?? []) }
            return false
        }()
        if case .edit(let movement) = mode, amountText == prefilledAmountText, !storedForeign || isForeign {
            // Untouched: send the stored value, digit for digit (the original amount for a foreign row).
            amount = storedForeign ? movement.originalAmount : movement.amount
        } else {
            amount = AmountInput.parse(amountText, separators: format.separators)
        }
        if amount == nil {
            errors[.amount] = tx("Escribí un monto mayor que cero, por ejemplo \(format.string(18_450).replacingOccurrences(of: format.symbol, with: "")).",
                                 "Enter an amount above zero, for example \(format.string(18_450).replacingOccurrences(of: format.symbol, with: "")).")
        }
        var rate: Decimal?
        if isForeign {
            if case .edit(let movement) = mode, storedForeign, rateText == prefilledRateText {
                rate = movement.exchangeRate // untouched stored rate
            } else {
                rate = RateInput.parse(rateText, separators: format.separators)
            }
            if rate == nil {
                errors[.rate] = tx("Escribí cuántos colones vale 1 dólar, por ejemplo \(format.inputText(Decimal(string: "507.5")!)).",
                                   "Enter how many colones 1 dollar is worth, for example \(format.inputText(Decimal(string: "507.5")!)).")
            }
        }
        if description.trimmingCharacters(in: .whitespaces).isEmpty {
            errors[.description] = tx("Escribí una descripción.", "Enter a description.")
        }
        fieldErrors = errors
        if errors.count > 1 { summaryFocused = true }
        guard errors.isEmpty, let amount else { return nil }
        return (amount, rate)
    }

    private func save() async {
        guard !saving, let validated = validate() else { return }
        let amount = validated.amount, rate = validated.rate
        saving = true
        saveError = nil
        defer { saving = false }
        let day = Self.dayFormatter.string(from: date)
        let text = description.trimmingCharacters(in: .whitespaces)
        do {
            switch mode {
            case .create:
                let entry = EntryCreate(amount: amount, description: text, category: category, entryDate: day,
                                        currency: isForeign ? currency : nil, exchangeRate: isForeign ? rate : nil)
                let key = (submission?.body == entry ? submission?.key : nil) ?? IdempotencyKey.new()
                submission = (entry, key)
                try await model.service.create(kind, entry, idempotencyKey: key)
            case .edit(let movement):
                try await model.service.update(movementID: movement.movementId, MovementUpdate(
                    transactionDate: day, description: text, amount: amount, transactionType: movement.transactionType,
                    category: category, notes: movement.notes ?? "", currency: isForeign ? currency : nil, exchangeRate: isForeign ? rate : nil))
            }
            saved += 1
            onSaved(isEditing ? tx("Cambios guardados", "Changes saved") : (kind == .income ? tx("Ingreso guardado", "Income saved") : tx("Gasto guardado", "Expense saved")))
            dismiss()
        } catch let error as APIError where error.kind == .notFound && isEditing {
            // Deleted or locked elsewhere: nothing to save; the list refreshes and says so.
            onSaved(tx("Ese movimiento ya no existe. Actualizamos la lista.", "That transaction no longer exists. The list was refreshed."))
            dismiss()
        } catch let error as APIError {
            saveError = error.message
        } catch is CancellationError {
            return
        } catch AuthError.signedOut {
            await model.signOut()
        } catch {
            saveError = tx("No pudimos guardar. Revisá tu conexión e intentá de nuevo.", "We couldn’t save. Check your connection and try again.")
        }
    }

    static let dayFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = .current
        formatter.dateFormat = "yyyy-MM-dd"
        return formatter
    }()
}
