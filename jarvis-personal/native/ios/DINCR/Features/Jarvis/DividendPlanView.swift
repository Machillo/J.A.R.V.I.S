import DincrCore
import DincrDesign
import SwiftUI

/// JARVIS → Patrimonio → Inversiones: "Plan de dividendos". One field, the monthly goal: it answers how
/// much more to buy of the stocks already held, with net dividends reinvested, and what to buy this month only when the plan allows it
/// (no debt at 10% a year or more, 3 months of Salvavidas). Opening it only reads. The form brings the
/// stock's yield from an outside service, and it can be typed when that fails. Android: `DividendPlanCard`.
struct DividendPlanCard: View {
    @Environment(AppModel.self) private var model
    @State private var editing: DividendPlan?
    @State private var reloadToken = 0

    var body: some View {
        AsyncContent(fallback: tx("No pudimos cargar tu plan de dividendos.", "We couldn’t load your dividend plan."),
                     load: { try await model.service.dividendPlan() }) { plan, _ in
            content(plan)
                .sheet(item: Binding(get: { editing.map(EditingPlan.init) }, set: { editing = $0?.plan })) { item in
                    DividendPlanSheet(plan: item.plan) { reloadToken += 1 }
                }
        }
        .id(reloadToken)
    }

    private struct EditingPlan: Identifiable {
        let plan: DividendPlan
        var id: String { "dividend-plan" }
    }

    private func content(_ plan: DividendPlan) -> some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Text(tx("¿Cuánto querés ganar al mes en dividendos?", "How much do you want to earn monthly in dividends?"))
                .font(DincrFont.body.weight(.semibold))
            GoalField(plan: plan) { reloadToken += 1 }
            if plan.isConfigured, !plan.result.ready {
                Text(tx("No pudimos traer el dividendo de tu acción. Escribilo en Cambiar acciones.", "We couldn’t bring your stock’s dividend. Type it in Change stocks."))
                    .font(DincrFont.bodySmall)
                    .accessibilityIdentifier("wealth.dividends.incomplete")
            } else if plan.isConfigured {
                figures(plan)
            }
            Button(tx("Cambiar acciones", "Change stocks")) { editing = plan }
                .font(DincrFont.bodySmall.weight(.semibold)).foregroundStyle(.dincrTint).frame(minHeight: 44)
                .accessibilityIdentifier("wealth.dividends.edit")
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .dincrCard()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("wealth.dividends")
    }

    /// One number, one answer: reads what is held and calculates. Stores only the goal and those stocks.
    private struct GoalField: View {
        @Environment(AppModel.self) private var model
        let plan: DividendPlan
        let done: () -> Void
        @State private var text = ""
        @State private var error: String?
        @State private var working = false

        var body: some View {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                HStack(spacing: DincrSpacing.s2) {
                    Text("US$").foregroundStyle(.dincrTextMuted).accessibilityHidden(true)
                    TextField(tx("Tu meta al mes", "Your monthly goal"), text: $text)
                        .keyboardType(.decimalPad).font(DincrFont.body.monospacedDigit())
                        .accessibilityIdentifier("wealth.dividends.goal")
                    Button(tx("Calcular", "Calculate")) { Task { await calculate() } }
                        .buttonStyle(.dincrPrimary(loading: working)).disabled(working).fixedSize()
                        .accessibilityIdentifier("wealth.dividends.calculate")
                }
                if let error { Text(error).font(DincrFont.caption).foregroundStyle(DincrColor.negative).accessibilityIdentifier("wealth.dividends.error") }
            }
            .onAppear { if text.isEmpty { text = plan.config.goalMonthlyUsd.map(model.moneyFormat.inputText) ?? "" } }
        }

        private func calculate() async {
            guard let goal = CorrectionInput.amount(text, separators: model.moneyFormat.separators) else {
                error = tx("Escribí cuánto querés ganar al mes.", "Enter how much you want to earn monthly."); return
            }
            working = true; error = nil
            defer { working = false }
            let epoch = model.currentEpoch
            do {
                _ = try await model.service.calculateDividendGoal(goal)
                done()
            } catch {
                self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos calcular.", "We couldn’t calculate."))
            }
        }
    }

    @ViewBuilder private func figures(_ plan: DividendPlan) -> some View {
        let result = plan.result
        ForEach(plan.config.stocks, id: \.symbol) { stock in
            if let yield = stock.yieldPct {
                Text(tx("\(stock.symbol) paga cerca de \(yield) % al año", "\(stock.symbol) pays about \(yield) % a year"))
                    .font(DincrFont.bodySmall).foregroundStyle(.dincrText2)
            }
        }
        FigureRow(label: tx("Necesitás tener invertido", "You need invested"), amount: result.capitalNeededUsd, currency: "USD")
        FigureRow(label: tx("Ya tenés", "You already have"), amount: result.currentValueUsd, currency: "USD")
        FigureRow(label: tx("Te falta comprar", "Still to buy"), amount: result.missingUsd, currency: "USD", emphasized: true)
        FigureRow(label: tx("Hoy te daría al mes", "It would pay you monthly today"), amount: result.netMonthlyDividendNowUsd, currency: "USD")
        if !result.monthlyNeeded.isEmpty {
            Text(tx("Con los dividendos reinvertidos, comprando cada mes:", "With dividends reinvested, buying every month:")).font(DincrFont.label).foregroundStyle(.dincrText2)
            ForEach(result.monthlyNeeded, id: \.years) { horizon in
                FigureRow(label: tx("Para llegar en \(horizon.years) años", "To get there in \(horizon.years) years"), amount: horizon.amountUsd, currency: "USD")
            }
        }
        if let line = Self.pace(result.monthsToGoal, amount: plan.config.monthlyAmountUsd) {
            Text(line).font(DincrFont.bodySmall).accessibilityIdentifier("wealth.dividends.pace")
        }
        if plan.gate.open {
            if !result.buyThisMonth.isEmpty {
                Text(tx("Este mes comprá", "This month, buy")).font(DincrFont.label).foregroundStyle(.dincrText2)
                ForEach(result.buyThisMonth, id: \.symbol) { FigureRow(label: $0.symbol, amount: $0.amountUsd, currency: "USD") }
            }
        } else {
            VStack(alignment: .leading, spacing: DincrSpacing.s1) {
                Text(tx("Todavía no te toca comprar más", "It’s not time to buy more yet")).font(DincrFont.bodySmall.weight(.semibold)).foregroundStyle(DincrColor.warning)
                ForEach(plan.gate.blockers, id: \.code) { Text(Self.blocker($0.code)).font(DincrFont.bodySmall) }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("wealth.dividends.gate")
        }
        Text(tx("Es un cálculo con el dividendo del último año, después de la retención del 30%, y con dividendos reinvertidos. Supone que el precio y el dividendo no cambian; pueden cambiar. No es asesoría de inversión.",
                "It’s a calculation with last year’s dividend, after the 30% withholding, with dividends reinvested. It assumes price and dividend stay the same; they can change. This isn’t investment advice."))
            .font(DincrFont.caption).foregroundStyle(.dincrTextMuted)
    }

    private static func pace(_ months: Int?, amount: Decimal?) -> String? {
        guard let months else { return nil }
        if months == 0 { return tx("Ya llegaste a tu meta.", "You’ve reached your goal.") }
        let years = months / 12, rest = months % 12
        let time = switch (years, rest) {
        case (0, _): tx("\(rest) meses", "\(rest) months")
        case (_, 0): tx("\(years) años", "\(years) years")
        default: tx("\(years) años y \(rest) meses", "\(years) years and \(rest) months")
        }
        return (amount ?? 0) > 0 ? tx("Con tu aporte mensual llegás en \(time).", "With your monthly amount you get there in \(time).")
            : tx("Sin aportar más llegás en \(time).", "Without adding more you get there in \(time).")
    }

    private static func blocker(_ code: String) -> String {
        switch code {
        case "expensive_debt": tx("Tenés deuda con tasa anual de 10% o más.", "You have debt at 10% a year or more.")
        case "debt_rate_unknown": tx("Falta la tasa de interés de una deuda.", "A debt’s interest rate is missing.")
        case "salvavidas_short": tx("El Salvavidas todavía no cubre 3 meses.", "The emergency fund doesn’t cover 3 months yet.")
        case "salvavidas_unknown": tx("Falta el saldo o el costo mensual del Salvavidas.", "The emergency fund’s balance or monthly cost is missing.")
        default: tx("Falta un dato para decidirlo.", "Some information is missing to decide.")
        }
    }
}

/// The plan's form. Saving only stores the plan: it buys nothing. Sent once, never retried.
private struct DividendPlanSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let plan: DividendPlan
    let onSaved: () -> Void
    @State private var symbolA = ""
    @State private var shareA = "100"
    @State private var yieldA = ""
    @State private var symbolB = ""
    @State private var shareB = ""
    @State private var yieldB = ""
    @State private var goal = ""
    @State private var monthly = ""
    @State private var withholding = ""
    @State private var error: String?
    @State private var saving = false
    @State private var yieldNote: String?

    var body: some View {
        NavigationStack {
            Form {
                Section(tx("Primera acción", "First stock")) {
                    field(tx("Símbolo", "Symbol"), $symbolA, id: "wealth.dividends.symbolA").textInputAutocapitalization(.characters).autocorrectionDisabled()
                    field(tx("Parte de lo que comprás (%)", "Share of what you buy (%)"), $shareA, id: "wealth.dividends.shareA").keyboardType(.decimalPad)
                    field(tx("Dividendo anual (%)", "Yearly dividend (%)"), $yieldA, id: "wealth.dividends.yieldA").keyboardType(.decimalPad)
                    Button(tx("Traer el dividendo de esta acción", "Bring this stock’s dividend")) { Task { await bringYield(symbolA) { yieldA = $0 } } }
                        .accessibilityIdentifier("wealth.dividends.bringA")
                    if let yieldNote { Text(yieldNote).font(DincrFont.caption).foregroundStyle(.dincrTextMuted).accessibilityIdentifier("wealth.dividends.yieldNote") }
                }
                Section(tx("Segunda acción (opcional)", "Second stock (optional)")) {
                    field(tx("Símbolo", "Symbol"), $symbolB, id: "wealth.dividends.symbolB").textInputAutocapitalization(.characters).autocorrectionDisabled()
                    field(tx("Parte de lo que comprás (%)", "Share of what you buy (%)"), $shareB, id: "wealth.dividends.shareB").keyboardType(.decimalPad)
                    field(tx("Dividendo anual (%)", "Yearly dividend (%)"), $yieldB, id: "wealth.dividends.yieldB").keyboardType(.decimalPad)
                    Button(tx("Traer el dividendo de esta acción", "Bring this stock’s dividend")) { Task { await bringYield(symbolB) { yieldB = $0 } } }
                        .accessibilityIdentifier("wealth.dividends.bringB")
                }
                Section {
                    field(tx("Meta de dividendos al mes (US$)", "Monthly dividend goal (US$)"), $goal, id: "wealth.dividends.goal").keyboardType(.decimalPad)
                    field(tx("Cuánto comprarías al mes (US$)", "How much you’d buy monthly (US$)"), $monthly, id: "wealth.dividends.monthly").keyboardType(.decimalPad)
                    field(tx("Retención de impuestos (%)", "Tax withholding (%)"), $withholding, id: "wealth.dividends.withholding").keyboardType(.decimalPad)
                } footer: {
                    Text(tx("La retención suele ser 30% en acciones de EE. UU.; confirmala con tu bróker.",
                            "Withholding is usually 30% on US stocks; confirm it with your broker."))
                }
                if let error {
                    Text(error).font(DincrFont.caption).foregroundStyle(DincrColor.negative).accessibilityIdentifier("wealth.dividends.error")
                }
            }
            .navigationTitle(tx("Plan de dividendos", "Dividend plan"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(tx("Cancelar", "Cancel")) { dismiss() }.disabled(saving) }
                ToolbarItem(placement: .confirmationAction) {
                    Button(tx("Guardar", "Save")) { Task { await save() } }.disabled(saving).accessibilityIdentifier("wealth.dividends.save")
                }
            }
            .onAppear(perform: prefill)
            // First time: the stock held is already there, so its dividend comes too.
            .task { if yieldA.isEmpty, !symbolA.isEmpty { await bringYield(symbolA) { yieldA = $0 } } }
        }
        .interactiveDismissDisabled(saving)
    }

    /// The label stays above the field once it has a value ("100" or "30" alone say nothing).
    private func field(_ label: String, _ text: Binding<String>, id: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(DincrFont.caption).foregroundStyle(.dincrText2).accessibilityHidden(true)
            TextField(label, text: text, prompt: Text("")).accessibilityIdentifier(id)
        }
    }

    /// Fills the field with the yield found; a failure is said and the field stays as it was, to type it.
    private func bringYield(_ symbol: String, into fill: (String) -> Void) async {
        let trimmed = symbol.trimmingCharacters(in: .whitespaces).uppercased()
        guard !trimmed.isEmpty else { yieldNote = tx("Escribí primero el símbolo.", "Enter the symbol first."); return }
        do {
            let found = try await model.service.dividendYield(symbol: trimmed)
            fill(plain(found.yieldPct))
            yieldNote = tx("\(trimmed): \(plain(found.yieldPct)) % según los dividendos del último año. Podés cambiarlo.",
                           "\(trimmed): \(plain(found.yieldPct)) % from the last year of dividends. You can change it.")
        } catch {
            yieldNote = tx("No pudimos traer el dividendo de \(trimmed). Podés escribirlo vos.", "We couldn’t bring \(trimmed)’s dividend. You can type it.")
        }
    }

    private func prefill() {
        let stocks = plan.config.stocks
        // First time: the stock already held in the portfolio, so it isn't typed again.
        symbolA = stocks.first?.symbol ?? plan.heldSymbols.first ?? ""
        shareA = stocks.first.map { plain($0.sharePct) } ?? "100"
        yieldA = stocks.first?.yieldPct.map(plain) ?? ""
        if stocks.count > 1 {
            symbolB = stocks[1].symbol; shareB = plain(stocks[1].sharePct); yieldB = stocks[1].yieldPct.map(plain) ?? ""
        }
        goal = plan.config.goalMonthlyUsd.map(model.moneyFormat.inputText) ?? ""
        monthly = plan.config.monthlyAmountUsd.map(model.moneyFormat.inputText) ?? ""
        withholding = plan.config.withholdingPct.map(plain) ?? ""
    }

    private func plain(_ value: Decimal) -> String { "\(value)" }

    private func number(_ text: String) -> Decimal? {
        let trimmed = text.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: ",", with: ".")
        return Decimal(string: trimmed, locale: Locale(identifier: "en_US_POSIX"))
    }

    private func save() async {
        guard !saving else { return }
        let first = symbolA.trimmingCharacters(in: .whitespaces), second = symbolB.trimmingCharacters(in: .whitespaces)
        guard !first.isEmpty else { error = tx("Escribí el símbolo de tu acción.", "Enter your stock’s symbol."); return }
        var stocks: [DividendPlan.Stock] = []
        for (symbol, share, yield) in [(first, shareA, yieldA), (second, shareB, yieldB)] where !symbol.isEmpty {
            guard let shareValue = number(share), yield.isEmpty || number(yield) != nil else {
                error = tx("Revisá los porcentajes.", "Check the percentages."); return
            }
            stocks.append(.init(symbol: symbol.uppercased(), sharePct: shareValue, yieldPct: yield.isEmpty ? nil : number(yield)))
        }
        // Amounts in the user's separators ("1.000" is a thousand); 0 is a valid monthly amount.
        let separators = model.moneyFormat.separators
        let goalValue = goal.isEmpty ? nil : CorrectionInput.amount(goal, separators: separators)
        let monthlyValue = monthly.isEmpty ? nil : CorrectionInput.amountZeroOrMore(monthly, separators: separators)
        guard (goal.isEmpty || goalValue != nil), (monthly.isEmpty || monthlyValue != nil), (withholding.isEmpty || number(withholding) != nil) else {
            error = tx("Revisá los montos.", "Check the amounts."); return
        }
        saving = true; error = nil
        defer { saving = false }
        let epoch = model.currentEpoch
        do {
            _ = try await model.service.updateDividendPlan(DividendPlanUpdate(stocks: stocks, goalMonthlyUsd: goalValue, monthlyAmountUsd: monthlyValue, withholdingPct: number(withholding)))
            onSaved()
            dismiss()
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos guardar.", "We couldn’t save."))
        }
    }
}
