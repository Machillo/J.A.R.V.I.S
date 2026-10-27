import DincrCore
import DincrDesign
import SwiftUI

/// PARITY D1, D3, D4, D5, D6 (partial: no debt or category filter yet) — movements by day,
/// search, type filter, add, edit, delete. The backend returns the whole history; search and the
/// type filter only narrow what is already on screen. The debt filter (D2) and debt
/// classification wait for the backend `kind` (audit §5).
struct MovementsView: View {
    enum Filter: String, CaseIterable, Identifiable {
        case all, income, expense
        var id: String { rawValue }
        var title: String {
            switch self {
            case .all: tx("Todos", "All")
            case .income: tx("Ingresos", "Income")
            case .expense: tx("Gastos", "Expenses")
            }
        }
    }

    @Environment(AppModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var state: LoadState<[Movement]> = .loading
    @State private var query = ""
    @State private var filter: Filter = .all
    @State private var editor: MovementEditor.Mode?
    @State private var pendingDelete: Movement?
    @State private var status: String?
    @State private var deleteError: String?
    /// Dollar expenses waiting for the close: no colones amount yet, so listed apart (never ₡0).
    @State private var pending: PendingConversion = .unavailable
    /// The close being confirmed (one rate for one period).
    @State private var closing: PendingConversion.Period?

    var body: some View {
        List {
            Section {
                Picker(tx("Tipo", "Type"), selection: $filter) {
                    ForEach(Filter.allCases) { Text($0.title).tag($0) }
                }
                .pickerStyle(.segmented)
                .listRowBackground(Color.clear)
                .listRowInsets(EdgeInsets())
                .sensoryFeedback(.selection, trigger: filter)
            }
            // UX-13: Movimientos → Análisis (monthly summary, reports, monthly review).
            Section {
                NavigationLink { AnalysisHubView() } label: { Label(tx("Análisis", "Analysis"), systemImage: "chart.bar.doc.horizontal") }
                    .accessibilityIdentifier("movements.analysis")
                // §15 PR 6: Movimientos → Por revisar — the bank notices detected in mail, reviewed in the
                // existing Email Monitor (the same screen as Perfil's; VIP and the Owner, locked below).
                if model.planTier == .vip {
                    // Back from the review, the list reloads: a confirmed notice is now a movement (as on Android).
                    NavigationLink { EmailMonitorView().onDisappear { Task { await load() } } } label: { Label(tx("Por revisar", "To review"), systemImage: "tray") }
                        .accessibilityIdentifier("movements.review")
                } else {
                    LockedListRow(title: tx("Por revisar", "To review"), symbol: "tray", tier: .vip, id: "movements.review")
                }
            }
            if let status {
                Section {
                    Label(status, systemImage: "checkmark.circle")
                        .foregroundStyle(DincrColor.positive)
                        .accessibilityIdentifier("movements.status")
                }
            }
            switch state {
            case .loading:
                Section { SkeletonView(rows: 5, showsFigure: false).listRowInsets(EdgeInsets()) }
                    .listRowBackground(Color.clear)
            case .failed(let message):
                Section { ErrorStateView(message: message) { Task { await load() } } }
                    .listRowBackground(Color.clear)
                    .listRowInsets(EdgeInsets())
            case .loaded(let rows):
                let groups = grouped(rows)
                if groups.isEmpty {
                    Section {
                        EmptyStateView(
                            symbol: rows.isEmpty ? "tray" : "magnifyingglass",
                            title: rows.isEmpty ? tx("Todavía no hay movimientos", "No transactions yet") : tx("Nada coincide con tu búsqueda", "Nothing matches your search"),
                            message: rows.isEmpty ? tx("Registrá tu primer ingreso o gasto para empezar.", "Record your first income or expense to begin.") : tx("Probá otra palabra o cambiá el filtro.", "Try another word or change the filter.")
                        ) {
                            if rows.isEmpty {
                                Button(tx("Agregar movimiento", "Add transaction")) { editor = .create }.buttonStyle(.dincrPrimary)
                            }
                        }
                    }
                    .listRowBackground(Color.clear)
                    .listRowInsets(EdgeInsets())
                }
                if filter != .income, !visiblePending.isEmpty { pendingSection }
                ForEach(groups, id: \.day) { group in
                    Section(DayLabel.format(group.day)) {
                        ForEach(group.rows) { row($0) }
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .dincrScreenBackground()
        .navigationTitle(tx("Movimientos", "Transactions"))
        .searchable(text: $query, prompt: tx("Buscar movimientos", "Search transactions"))
        .refreshable { await load() }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button { editor = .create } label: { Label(tx("Agregar movimiento", "Add transaction"), systemImage: "plus") }
                    .accessibilityIdentifier("movements.add")
            }
        }
        .sheet(item: $editor) { mode in
            MovementEditor(mode: mode, latestRate: latestRate) { message in
                announce(message)
                Task { await load() }
            }
        }
        .sheet(item: $closing) { period in
            ClosePeriodSheet(period: period, latestRate: latestRate) { message in
                announce(message)
                Task { await load() }
            }
        }
        .confirmationDialog(
            pendingDelete.map { tx("¿Eliminar «\($0.description ?? "movimiento")»?", "Delete “\($0.description ?? "transaction")”?") } ?? "",
            isPresented: Binding(get: { pendingDelete != nil }, set: { if !$0 { pendingDelete = nil } }),
            titleVisibility: .visible
        ) {
            Button(tx("Eliminar", "Delete"), role: .destructive) { if let row = pendingDelete { Task { await delete(row) } } }
            Button(tx("Cancelar", "Cancel"), role: .cancel) {}
        } message: {
            Text(tx("Esta acción no se puede deshacer.", "This can’t be undone."))
        }
        .alert(tx("No pudimos eliminarlo", "We couldn’t delete it"), isPresented: Binding(get: { deleteError != nil }, set: { if !$0 { deleteError = nil } })) {
            Button(tx("Entendido", "OK"), role: .cancel) {}
        } message: { Text(deleteError ?? "") }
        .task { if case .loading = state { await load() } }
        // New mail on return (AppModel.syncOnReturn): read again, keeping the list if it fails.
        .onChange(of: model.dataGeneration) { _, _ in Task { await load(keepOnFailure: true) } }
        .animation(DincrMotion.standard(reduceMotion), value: state)
    }

    @ViewBuilder
    private func row(_ movement: Movement) -> some View {
        let editable = movement.canEdit(entryCurrencies: model.profile?.entryCurrencies ?? [])
        let content = MoneyRow(
            title: movement.description?.isEmpty == false ? movement.description! : CategoryStyle.label(movement.category),
            subtitle: [CategoryStyle.label(movement.category), originalLabel(movement), editable ? nil : tx("Solo lectura", "Read only")].compactMap { $0 }.joined(separator: " · "),
            amount: movement.amount, kind: movement.transactionType,
            symbol: CategoryStyle.symbol(for: movement.category, kind: movement.transactionType),
            isReadOnly: !editable
        )
        if editable {
            Button { editor = .edit(movement) } label: { content }
                .buttonStyle(.plain)
                .swipeActions(edge: .trailing) {
                    Button(tx("Eliminar", "Delete"), role: .destructive) { pendingDelete = movement }
                }
                .contextMenu {
                    Button(tx("Editar", "Edit"), systemImage: "pencil") { editor = .edit(movement) }
                    Button(tx("Eliminar", "Delete"), systemImage: "trash", role: .destructive) { pendingDelete = movement }
                }
                .accessibilityHint(tx("Tocá para editar", "Tap to edit"))
        } else {
            content
        }
    }

    private var visiblePending: [PendingConversion.Item] {
        pending.items.filter { SearchText.matches(query, in: [$0.description, $0.category]) }
    }

    /// The dollars that accumulate until the close, beside the colones list: one section per close
    /// (a card's statement cycle, or a calendar month), with its total and, once it has ended, the
    /// conversion with one rate. A server without the close lists them in one section.
    @ViewBuilder
    private var pendingSection: some View {
        if pending.periods.isEmpty {
            Section {
                ForEach(pending.totals) { pendingTotal($0) }
                ForEach(visiblePending) { pendingRow($0) }
            } header: {
                Text(tx("En dólares · se convierten al cierre", "In dollars · converted at the close"))
            }
        } else {
            ForEach(pending.periods) { period in
                let items = visiblePending.filter { $0.periodKey == period.key }
                if !items.isEmpty {
                    Section {
                        ForEach(period.totals) { pendingTotal($0) }
                        ForEach(items) { pendingRow($0) }
                        if period.closable {
                            Button(tx("Convertir a colones", "Convert to colones")) { closing = period }
                                .fontWeight(.semibold)
                                .accessibilityIdentifier("movements.pending.close.\(period.key)")
                        }
                    } header: {
                        Text(tx("En dólares · \(PendingPeriodLabel.title(period))", "In dollars · \(PendingPeriodLabel.title(period))"))
                    } footer: {
                        VStack(alignment: .leading, spacing: 2) {
                            if !period.closable {
                                Text(tx("Se convierte desde el \(DayLabel.format(period.end)), con un solo tipo de cambio.",
                                        "It converts from \(DayLabel.format(period.end)), with one rate."))
                            }
                            if period.cutDayMissing {
                                Text(tx("Una tarjeta no tiene día de corte: se cierra a fin de mes. Declaralo en Cuentas para cerrarla por su corte.",
                                        "A card has no cut day: it closes at month end. Declare it in Accounts to close it by its cut."))
                            }
                        }
                    }
                }
            }
        }
    }

    private func pendingTotal(_ total: PendingConversion.Total) -> some View {
        HStack {
            Text(tx("Total por convertir", "Total to convert")).font(DincrFont.body.weight(.semibold))
            Spacer()
            Text(model.moneyFormat.string(total.amount, currency: total.currency)).font(DincrFont.amount)
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("movements.pending.total.\(total.currency)")
    }

    private func pendingRow(_ item: PendingConversion.Item) -> some View {
        Button { editor = .edit(item.movement) } label: {
            MoneyRow(title: item.description.isEmpty ? CategoryStyle.label(item.category) : item.description,
                     subtitle: [CategoryStyle.label(item.category), DayLabel.format(item.entryDate)].joined(separator: " · "),
                     amount: item.originalAmount, kind: .expense,
                     symbol: CategoryStyle.symbol(for: item.category, kind: .expense), currency: item.originalCurrency)
        }
        .buttonStyle(.plain)
        .swipeActions(edge: .trailing) {
            Button(tx("Eliminar", "Delete"), role: .destructive) { pendingDelete = item.movement }
        }
        .accessibilityIdentifier("movements.pending.\(item.id)")
        .accessibilityHint(tx("Tocá para editar", "Tap to edit"))
    }

    /// "US$10 × 507,5" for a row typed in another currency: the original figure and the user's rate.
    private func originalLabel(_ movement: Movement) -> String? {
        guard let original = movement.originalAmount, let code = movement.originalCurrency else { return nil }
        let format = model.moneyFormat
        let rate = movement.exchangeRate.map { " × \(format.inputText($0))" } ?? ""
        return format.string(original, currency: code) + rate
    }

    private var latestRate: Decimal? {
        if case .loaded(let rows) = state { return ConversionPreview.latestUserRate(rows) }
        return nil
    }

    private func grouped(_ rows: [Movement]) -> [(day: String, rows: [Movement])] {
        let visible = rows.filter { row in
            (filter == .all || row.transactionType.rawValue == filter.rawValue)
                && SearchText.matches(query, in: [row.description, row.category])
        }
        let byDay = Dictionary(grouping: visible) { $0.day ?? "" }
        return byDay.keys.sorted(by: >).map { (day: $0, rows: byDay[$0]!) }
    }

    /// Loads the list. A reload that fails while the list is shown (pull to refresh, after a save
    /// or a delete) keeps it and says so in the app notice (B17, `PullRefresh`); only a first load
    /// without a list shows the error. An answer from another session is dropped.
    private func load(keepOnFailure: Bool = false) async {
        let epoch = model.currentEpoch
        let shown: [Movement]? = if case .loaded(let rows) = state { rows } else { nil }
        do {
            let rows = try await model.service.movements()
            // Optional: the pending dollars never hide the colones list when they can't be read.
            let waiting = (try? await model.service.pendingConversion()) ?? .unavailable
            if epoch == model.currentEpoch { pending = waiting; state = .loaded(rows) }
        } catch is CancellationError {
            return
        } catch {
            if keepOnFailure, case .loaded = state { return }
            guard let message = model.message(for: error, epoch: epoch,
                                              fallback: tx("No pudimos cargar tus movimientos.", "We couldn’t load your transactions.")) else { return }
            if PullRefresh.kept(shown, after: .failure(error)) != nil {
                model.notice = PullRefresh.failureNotice()
            } else {
                state = .failed(message)
            }
        }
    }

    private func delete(_ movement: Movement) async {
        pendingDelete = nil
        do {
            try await model.service.delete(movementID: movement.movementId)
            announce(tx("Movimiento eliminado", "Transaction deleted"))
            await load()
        } catch let error as APIError where error.kind == .notFound {
            // Already gone (deleted elsewhere or twice): show the list as it really is.
            announce(tx("Ese movimiento ya no existía.", "That transaction was already gone."))
            await load()
        } catch let error as APIError {
            deleteError = error.message
        } catch AuthError.signedOut {
            await model.signOut()
        } catch {
            deleteError = tx("Intentá de nuevo.", "Please try again.")
        }
    }

    /// iOS has no toasts: the change is visible in place; this row confirms it and is read out.
    private func announce(_ message: String) {
        status = message
        AccessibilityNotification.Announcement(message).post()
        Task {
            try? await Task.sleep(for: .seconds(4))
            if status == message { status = nil }
        }
    }
}

/// "Hoy", "Ayer", or "12 de setiembre".
enum DayLabel {
    static func format(_ day: String, today: Date = .now, language: AppLanguage = .current) -> String {
        guard !day.isEmpty else { return language.pick("Sin fecha", "No date") }
        let parser = DateFormatter()
        parser.calendar = Calendar(identifier: .gregorian)
        parser.locale = Locale(identifier: "en_US_POSIX")
        parser.dateFormat = "yyyy-MM-dd"
        guard let date = parser.date(from: day) else { return day }
        let calendar = Calendar.current
        if calendar.isDate(date, inSameDayAs: today) { return language.pick("Hoy", "Today") }
        if let yesterday = calendar.date(byAdding: .day, value: -1, to: today), calendar.isDate(date, inSameDayAs: yesterday) {
            return language.pick("Ayer", "Yesterday")
        }
        let output = DateFormatter()
        output.locale = Locale(identifier: language == .spanish ? "es_CR" : "en_US")
        output.setLocalizedDateFormatFromTemplate(calendar.isDate(date, equalTo: today, toGranularity: .year) ? "dMMMM" : "dMMMMyyyy")
        return output.string(from: date)
    }
}
