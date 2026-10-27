import DincrCore
import DincrDesign
import SwiftUI

/// JARVIS → Patrimonio (Owner only): the investments (the latest IBKR or manual portfolio snapshot
/// and its positions, "Actualizar desde IBKR") and the businesses (their totals and movements,
/// "Nuevo negocio", "Registrar movimiento"). Opening it only reads; every write is an explicit
/// Owner command, sent once and never retried on its own. Without a portfolio snapshot it says so
/// instead of showing ₡0 / 0 %. The net worth stays in Análisis financiero ("Ver patrimonio neto").
/// Android: `OwnerWealthScreen`.
struct WealthView: View {
    enum Tab: Hashable { case investments, businesses }

    @Environment(AppModel.self) private var model
    @State private var tab: Tab = .investments
    @State private var notice: String?
    @State private var reloadToken = 0
    @State private var syncing = false
    @State private var syncError: String?
    @State private var addingBusiness = false
    @State private var recording: BusinessCenter.Business?

    var body: some View {
        ScreenScroll(title: tx("Patrimonio", "Wealth")) {
            Picker(tx("Vista", "View"), selection: $tab) {
                Text(tx("Inversiones", "Investments")).tag(Tab.investments)
                Text(tx("Negocios", "Businesses")).tag(Tab.businesses)
            }
            .pickerStyle(.segmented)
            .accessibilityIdentifier("wealth.tab")
            if let notice { StatusBanner(tone: .info, title: notice, message: "").accessibilityIdentifier("wealth.notice") }
            switch tab {
            case .investments:
                AsyncContent(fallback: tx("No pudimos cargar tus inversiones.", "We couldn’t load your investments."),
                             load: { try await model.service.investmentCenter() }) { center, _ in
                    InvestmentsContent(center: center, syncing: syncing, syncError: syncError, sync: { Task { await sync() } })
                }
                .id(reloadToken)
            case .businesses:
                AsyncContent(fallback: tx("No pudimos cargar tus negocios.", "We couldn’t load your businesses."),
                             load: { try await model.service.businessCenter() }) { center, _ in
                    BusinessesContent(center: center, add: { addingBusiness = true }, record: { recording = $0 })
                }
                .id(reloadToken)
            }
            NavigationLink(value: ProfileRoute.jarvisSection(.analysis)) {
                HStack {
                    Text(tx("Ver patrimonio neto", "See net worth")).font(DincrFont.body.weight(.semibold)).foregroundStyle(DincrColor.tint)
                    Spacer()
                    Image(systemName: "chevron.right").foregroundStyle(DincrColor.textMuted).accessibilityHidden(true)
                }
                .dincrCard()
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("wealth.netWorth")
        }
        .sheet(isPresented: $addingBusiness) {
            BusinessEntrySheet { done($0) }
        }
        .sheet(item: $recording) { business in
            BusinessMovementSheet(business: business) { done($0) }
        }
    }

    private func done(_ message: String) {
        notice = message
        reloadToken += 1
    }

    /// "Actualizar desde IBKR": one request (the button is disabled while it runs), never retried on
    /// its own; the backend's error message is shown as is.
    private func sync() async {
        guard !syncing else { return }
        syncing = true; syncError = nil
        defer { syncing = false }
        let epoch = model.currentEpoch
        do {
            try await model.service.syncIbkr()
            done(tx("Portafolio actualizado", "Portfolio updated"))
        } catch {
            syncError = model.message(for: error, epoch: epoch, fallback: tx("No pudimos actualizar desde IBKR.", "We couldn’t update from IBKR."))
        }
    }
}

/// A percentage with up to two decimals in the app's language ("11,11 %").
private func percentLabel(_ value: Decimal) -> String {
    let formatter = NumberFormatter()
    formatter.locale = Locale(identifier: AppLanguage.current == .spanish ? "es_CR" : "en_US")
    formatter.numberStyle = .decimal
    formatter.maximumFractionDigits = 2
    return "\(formatter.string(from: NSDecimalNumber(decimal: value)) ?? "\(value)") %"
}

private struct InvestmentsContent: View {
    let center: InvestmentCenter
    let syncing: Bool
    let syncError: String?
    let sync: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            if let figures = center.figures {
                FigureRow(label: tx("Valor de mercado", "Market value"), amount: figures.marketValue, currency: figures.currency)
                FigureRow(label: tx("Capital aportado", "Contributed capital"), amount: figures.contributedCapital, currency: figures.currency)
                FigureRow(label: tx("Ganancia neta", "Net gain"), amount: figures.netPnl, currency: figures.currency)
                if let returnPct = figures.returnPct {
                    InfoRow(label: tx("Rendimiento", "Return"), value: percentLabel(returnPct))
                }
            } else {
                // Unknown ≠ 0: without a snapshot the backend's 0 figures are not shown.
                Text(tx("Todavía no hay datos de tu portafolio", "There’s no portfolio data yet"))
                    .font(DincrFont.bodySmall.weight(.semibold))
                    .accessibilityIdentifier("wealth.investments.empty")
            }
            if let caption = syncCaption {
                Text(caption).font(DincrFont.caption).foregroundStyle(center.syncState == .stale ? DincrColor.warning : DincrColor.textMuted)
            }
            FigureRow(label: tx("Reservado para invertir", "Reserved to invest"), amount: center.reservedToInvestCrc, currency: "CRC")
            if center.flexConfigured {
                Button(syncing ? tx("Actualizando…", "Updating…") : tx("Actualizar desde IBKR", "Update from IBKR"), action: sync)
                    .buttonStyle(.dincrSecondary)
                    .disabled(syncing)
                    .accessibilityIdentifier("wealth.sync")
            }
            if let syncError { Text(syncError).font(DincrFont.caption).foregroundStyle(DincrColor.negative) }
        }
        .dincrCard()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("wealth.investments")

        if !center.positions.isEmpty {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                Text(tx("Posiciones", "Positions")).font(DincrFont.label).foregroundStyle(DincrColor.text2)
                ForEach(center.positions) { position in
                    HStack(alignment: .firstTextBaseline) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(position.symbol ?? tx("Posición", "Position")).font(DincrFont.bodySmall.weight(.semibold))
                            if let quantity = position.quantity {
                                Text(tx("Cantidad: \(Self.quantity(quantity))", "Quantity: \(Self.quantity(quantity))"))
                                    .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                            }
                            if let pnl = position.unrealizedPnl {
                                HStack(spacing: 4) {
                                    Text(tx("Ganancia no realizada:", "Unrealized gain:")).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                                    MoneyText(pnl, currency: position.currency, font: DincrFont.caption)
                                }
                            }
                        }
                        Spacer()
                        MoneyText(position.marketValue, currency: position.currency)
                    }
                    .accessibilityElement(children: .combine)
                }
            }
            .dincrCard()
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("wealth.positions")
        }
    }

    private var syncCaption: String? {
        switch center.syncState {
        case .current:
            guard let hours = center.ageHours else { return tx("Actualizado", "Up to date") }
            return hours == 0 ? tx("Actualizado hace menos de 1 h", "Updated less than 1 h ago") : tx("Actualizado hace \(hours) h", "Updated \(hours) h ago")
        case .stale: return tx("Desactualizado", "Out of date")
        case .manual: return tx("Manual", "Manual")
        case .unknown: return nil
        }
    }

    private static func quantity(_ value: Decimal) -> String {
        let formatter = NumberFormatter()
        formatter.locale = Locale(identifier: AppLanguage.current == .spanish ? "es_CR" : "en_US")
        formatter.numberStyle = .decimal
        formatter.maximumFractionDigits = 4
        return formatter.string(from: NSDecimalNumber(decimal: value)) ?? "\(value)"
    }
}

private struct BusinessesContent: View {
    let center: BusinessCenter
    let add: () -> Void
    let record: (BusinessCenter.Business) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            FigureRow(label: tx("Ingresos", "Income"), amount: center.income)
            FigureRow(label: tx("Gastos", "Expenses"), amount: center.expenses)
            FigureRow(label: tx("Ganancia", "Profit"), amount: center.profit)
            FigureRow(label: tx("Capital aportado", "Capital contributed"), amount: center.capital)
            Button(tx("Nuevo negocio", "New business"), action: add)
                .buttonStyle(.dincrSecondary)
                .accessibilityIdentifier("wealth.addBusiness")
        }
        .dincrCard()
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("wealth.businesses")

        if center.businesses.isEmpty {
            EmptyStateView(symbol: "briefcase", title: tx("Todavía no tenés negocios", "You don’t have businesses yet"),
                           message: tx("Con «Nuevo negocio» registrás uno.", "Use “New business” to add one.")) { EmptyView() }
        }
        ForEach(center.businesses) { business in
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                Text(business.name ?? tx("Negocio", "Business")).font(DincrFont.body.weight(.semibold))
                if let description = business.description, !description.isEmpty {
                    Text(description).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                }
                if let ownership = business.ownershipPct {
                    InfoRow(label: tx("Participación", "Ownership"), value: percentLabel(ownership))
                }
                let movements = center.movements(of: business)
                if movements.isEmpty {
                    Text(tx("Sin movimientos todavía", "No movements yet")).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                }
                ForEach(movements) { movement in
                    HStack(alignment: .firstTextBaseline) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(movement.description ?? Self.typeLabel(movement.movementType)).font(DincrFont.bodySmall)
                            Text([Self.typeLabel(movement.movementType), movement.movementDate.map { Day.label($0) }].compactMap { $0 }.joined(separator: " · "))
                                .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                        }
                        Spacer()
                        MoneyText(movement.amount.map { movement.movementType == "expense" ? -$0 : $0 })
                    }
                    .accessibilityElement(children: .combine)
                }
                Button(tx("Registrar movimiento", "Record movement")) { record(business) }
                    .buttonStyle(.dincrSecondary)
                    .accessibilityIdentifier("wealth.addMovement.\(business.id)")
            }
            .dincrCard()
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("wealth.business.\(business.id)")
        }
    }

    static func typeLabel(_ type: String?) -> String {
        switch type {
        case "income": tx("Ingreso", "Income")
        case "expense": tx("Gasto", "Expense")
        case "capital": tx("Capital", "Capital")
        default: tx("Movimiento", "Movement")
        }
    }
}

/// "Nuevo negocio": saved once (disabled while it is sent), never retried on its own.
private struct BusinessEntrySheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let onDone: (String) -> Void
    @State private var name = ""
    @State private var detail = ""
    @State private var ownership = "100"
    @State private var error: String?
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField(tx("Nombre", "Name"), text: $name).accessibilityIdentifier("wealth.business.name")
                    TextField(tx("Descripción (opcional)", "Description (optional)"), text: $detail).accessibilityIdentifier("wealth.business.description")
                    TextField(tx("Participación (%)", "Ownership (%)"), text: $ownership).keyboardType(.decimalPad).accessibilityIdentifier("wealth.business.ownership")
                    if let error { Text(error).font(DincrFont.caption).foregroundStyle(DincrColor.negative) }
                }
            }
            .navigationTitle(tx("Nuevo negocio", "New business"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(tx("Cancelar", "Cancel")) { dismiss() }.disabled(saving) }
                ToolbarItem(placement: .confirmationAction) {
                    Button(tx("Guardar", "Save")) { Task { await submit() } }.disabled(saving).accessibilityIdentifier("wealth.business.save")
                }
            }
        }
        .interactiveDismissDisabled(saving)
    }

    private func submit() async {
        guard !saving else { return }
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { error = tx("Escribí el nombre del negocio.", "Enter the business name."); return }
        let percent = Decimal(string: ownership.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: ",", with: "."), locale: Locale(identifier: "en_US_POSIX"))
        guard let percent, percent >= 0, percent <= 100 else { error = tx("La participación va de 0 a 100.", "Ownership goes from 0 to 100."); return }
        saving = true; error = nil
        defer { saving = false }
        let epoch = model.currentEpoch
        let description = detail.trimmingCharacters(in: .whitespacesAndNewlines)
        do {
            try await model.service.createBusiness(BusinessCreateRequest(name: trimmed, description: description.isEmpty ? nil : description, ownershipPct: percent))
            onDone(tx("Negocio creado", "Business created"))
            dismiss()
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos crearlo. Revisá la lista antes de intentar de nuevo.", "We couldn’t create it. Check the list before trying again."))
        }
    }
}

/// "Registrar movimiento": an income, expense or capital contribution of one business. An income or
/// expense also lands in the Owner's transactions, and the form says so. Saved once, never retried.
private struct BusinessMovementSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let business: BusinessCenter.Business
    let onDone: (String) -> Void
    @State private var type = "income"
    @State private var text = ""
    @State private var detail = ""
    @State private var date = Day.today()
    @State private var error: String?
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Picker(tx("Tipo", "Type"), selection: $type) {
                        ForEach(BusinessMovementRequest.types, id: \.self) { Text(BusinessesContent.typeLabel($0)).tag($0) }
                    }
                    .pickerStyle(.segmented)
                    .accessibilityIdentifier("wealth.movement.type")
                    TextField(tx("Monto", "Amount"), text: $text).keyboardType(.decimalPad).accessibilityIdentifier("wealth.movement.amount")
                    TextField(tx("Descripción", "Description"), text: $detail).accessibilityIdentifier("wealth.movement.description")
                    TextField(tx("Fecha (AAAA-MM-DD)", "Date (YYYY-MM-DD)"), text: $date).keyboardType(.numbersAndPunctuation).accessibilityIdentifier("wealth.movement.date")
                    if type != "capital" {
                        Text(tx("También se registra en tus movimientos.", "It’s also recorded in your transactions."))
                            .font(DincrFont.caption).foregroundStyle(DincrColor.text2)
                            .accessibilityIdentifier("wealth.movement.ledgerNote")
                    }
                    if let error { Text(error).font(DincrFont.caption).foregroundStyle(DincrColor.negative) }
                }
            }
            .navigationTitle(business.name ?? tx("Registrar movimiento", "Record movement"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(tx("Cancelar", "Cancel")) { dismiss() }.disabled(saving) }
                ToolbarItem(placement: .confirmationAction) {
                    Button(tx("Registrar", "Record")) { Task { await submit() } }.disabled(saving).accessibilityIdentifier("wealth.movement.save")
                }
            }
        }
        .interactiveDismissDisabled(saving)
    }

    private func submit() async {
        guard !saving else { return }
        guard let amount = AmountInput.parse(text, separators: model.moneyFormat.separators) else {
            error = model.moneyFormat.amountHint
            return
        }
        let description = detail.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !description.isEmpty else { error = tx("Escribí una descripción.", "Enter a description."); return }
        let day = date.trimmingCharacters(in: .whitespaces)
        guard day.isEmpty || Day.formatter().date(from: day) != nil else { error = tx("Escribí la fecha como AAAA-MM-DD.", "Enter the date as YYYY-MM-DD."); return }
        saving = true; error = nil
        defer { saving = false }
        let epoch = model.currentEpoch
        do {
            try await model.service.addBusinessMovement(BusinessMovementRequest(businessId: business.id, movementType: type, amount: amount,
                                                                                movementDate: day.isEmpty ? nil : day, description: description))
            onDone(tx("Movimiento registrado", "Movement recorded"))
            dismiss()
        } catch {
            self.error = model.message(for: error, epoch: epoch, fallback: tx("No pudimos registrarlo. Revisá la lista antes de intentar de nuevo.", "We couldn’t record it. Check the list before trying again."))
        }
    }
}
