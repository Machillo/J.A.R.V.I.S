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
            MovementEditor(mode: mode) { message in
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
        .animation(DincrMotion.standard(reduceMotion), value: state)
    }

    @ViewBuilder
    private func row(_ movement: Movement) -> some View {
        let editable = movement.isEditable(baseCurrency: model.moneyFormat.currency)
        let content = MoneyRow(
            title: movement.description?.isEmpty == false ? movement.description! : CategoryStyle.label(movement.category),
            subtitle: [CategoryStyle.label(movement.category), editable ? nil : tx("Solo lectura", "Read only")].compactMap { $0 }.joined(separator: " · "),
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

    private func grouped(_ rows: [Movement]) -> [(day: String, rows: [Movement])] {
        let visible = rows.filter { row in
            (filter == .all || row.transactionType.rawValue == filter.rawValue)
                && SearchText.matches(query, in: [row.description, row.category])
        }
        let byDay = Dictionary(grouping: visible) { $0.day ?? "" }
        return byDay.keys.sorted(by: >).map { (day: $0, rows: byDay[$0]!) }
    }

    private func load() async {
        do {
            state = .loaded(try await model.service.movements())
        } catch let error as APIError {
            state = .failed(error.message)
        } catch is CancellationError {
            return
        } catch AuthError.signedOut {
            await model.signOut()
        } catch {
            state = .failed(tx("No pudimos cargar tus movimientos.", "We couldn’t load your transactions."))
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
