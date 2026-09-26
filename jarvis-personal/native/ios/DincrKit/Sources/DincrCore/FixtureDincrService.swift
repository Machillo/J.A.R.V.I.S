import Foundation

/// In-memory service with synthetic data for SwiftUI previews, UI tests and store/landing
/// screenshots. All names and amounts are invented (CLAUDE.md §4.F: no real data in fixtures).
///
/// It stores what the screens write so flows can be exercised end to end, but it does not
/// compute financial results: dashboard figures are fixed sample values, exactly like the
/// backend would return them.
public actor FixtureDincrService: DincrService {
    public enum Scenario: String, Sendable {
        case populated, empty, failing, newUser
    }

    private var profile: Profile
    private var rows: [Movement]
    private let scenario: Scenario
    private let latency: Duration
    private var nextID = 100

    public init(scenario: Scenario = .populated, latency: Duration = .milliseconds(350), today: Date = .now) {
        self.scenario = scenario
        self.latency = latency
        self.profile = Profile(
            id: "fixture-account", email: "ana@example.com", displayName: "Ana Solís",
            profileSetupCompleted: scenario != .newUser,
            subscription: .init(plan: "free", status: "active")
        )
        self.rows = scenario == .populated ? Self.sampleMovements(today: today) : []
    }

    public func me() async throws -> Profile {
        try await pause()
        return profile
    }

    public func completeProfileSetup(_ setup: ProfileSetup) async throws -> Profile {
        try await pause()
        profile = Profile(
            id: profile.id, email: profile.email, displayName: setup.displayName,
            profileSetupCompleted: true, baseCurrency: setup.baseCurrency,
            numberFormat: setup.numberFormat, currencyPlacement: setup.currencyPlacement,
            subscription: profile.subscription
        )
        return profile
    }

    public func freeDashboard() async throws -> FreeDashboard {
        try await pause()
        if scenario == .empty || scenario == .newUser {
            return FreeDashboard(month: "2026-09", income: 0, expenses: 0, debtPaid: 0, debtBalance: nil, balance: 0,
                                 availableAfterCommitments: 0, categories: [], monthlyHistory: [])
        }
        return Self.sampleDashboard
    }

    public func movements() async throws -> [Movement] {
        try await pause()
        return rows.sorted { ($0.day ?? "") > ($1.day ?? "") }
    }

    public func create(_ kind: Movement.Kind, _ entry: EntryCreate) async throws {
        try await pause()
        nextID += 1
        let origin = kind == .income ? "salary" : "expense"
        rows.append(Movement(
            movementId: "\(origin):\(nextID)", sourceId: nextID, origin: origin, transactionDate: entry.entryDate,
            description: entry.description, amount: entry.amount, transactionType: kind, category: entry.category
        ))
    }

    public func update(movementID: String, _ update: MovementUpdate) async throws {
        try await pause()
        guard let index = rows.firstIndex(where: { $0.movementId == movementID }) else {
            throw APIError(kind: .notFound, status: 404, message: "Movimiento no encontrado o no editable.")
        }
        let old = rows[index]
        rows[index] = Movement(
            movementId: old.movementId, sourceId: old.sourceId, origin: old.origin, transactionDate: update.transactionDate,
            description: update.description, amount: update.amount, transactionType: old.transactionType,
            category: update.category, notes: update.notes, editable: old.editable
        )
    }

    public func delete(movementID: String) async throws {
        try await pause()
        rows.removeAll { $0.movementId == movementID }
    }

    private func pause() async throws {
        try await Task.sleep(for: latency)
        if scenario == .failing {
            throw APIError(kind: .server, status: 503, message: AppLanguage.current.pick(
                "DINCR no pudo completar la operación. Intentá de nuevo en unos segundos.",
                "DINCR couldn’t complete the operation. Try again in a few seconds."))
        }
    }

    static let sampleDashboard = FreeDashboard(
        month: "2026-09", income: 865_000, expenses: 512_450, debtPaid: 95_000, debtBalance: 1_240_000,
        balance: 257_550, availableAfterCommitments: 257_550,
        categories: [
            CategoryAmount(category: "Vivienda", amount: 210_000),
            CategoryAmount(category: "Comida", amount: 128_300),
            CategoryAmount(category: "Transporte", amount: 64_150),
            CategoryAmount(category: "Servicios", amount: 58_000),
            CategoryAmount(category: "Entretenimiento", amount: 32_000),
            CategoryAmount(category: "Salud", amount: 20_000),
        ],
        monthlyHistory: [
            MonthTotals(month: "2026-04", income: 820_000, expenses: 598_000, debtPaid: 95_000, balance: 127_000),
            MonthTotals(month: "2026-05", income: 820_000, expenses: 541_200, debtPaid: 95_000, balance: 183_800),
            MonthTotals(month: "2026-06", income: 905_000, expenses: 630_500, debtPaid: 95_000, balance: 179_500),
            MonthTotals(month: "2026-07", income: 840_000, expenses: 575_900, debtPaid: 95_000, balance: 169_100),
            MonthTotals(month: "2026-08", income: 865_000, expenses: 603_300, debtPaid: 95_000, balance: 166_700),
            MonthTotals(month: "2026-09", income: 865_000, expenses: 512_450, debtPaid: 95_000, balance: 257_550),
        ]
    )

    static func sampleMovements(today: Date) -> [Movement] {
        let calendar = Calendar(identifier: .gregorian)
        func day(_ offset: Int) -> String {
            let date = calendar.date(byAdding: .day, value: -offset, to: today) ?? today
            let parts = calendar.dateComponents([.year, .month, .day], from: date)
            return String(format: "%04d-%02d-%02d", parts.year!, parts.month!, parts.day!)
        }
        return [
            Movement(movementId: "expense:11", sourceId: 11, origin: "expense", transactionDate: day(0), description: "Supermercado", amount: 18_450, transactionType: .expense, category: "Comida"),
            Movement(movementId: "expense:10", sourceId: 10, origin: "expense", transactionDate: day(0), description: "Café", amount: 2_300, transactionType: .expense, category: "Restaurante"),
            Movement(movementId: "transaction:9", sourceId: 9, origin: "transaction", transactionDate: day(1), description: "Aviso bancario · Gasolinera", amount: 25_000, transactionType: .expense, category: "Gasolina", editable: false),
            Movement(movementId: "salary:8", sourceId: 8, origin: "salary", transactionDate: day(3), description: "Salario quincenal", amount: 432_500, transactionType: .income, category: "Salario"),
            Movement(movementId: "expense:7", sourceId: 7, origin: "expense", transactionDate: day(4), description: "Internet del hogar", amount: 24_900, transactionType: .expense, category: "Internet"),
            Movement(movementId: "expense:6", sourceId: 6, origin: "expense", transactionDate: day(6), description: "Farmacia", amount: 9_800, transactionType: .expense, category: "Salud"),
            Movement(movementId: "expense:5", sourceId: 5, origin: "expense", transactionDate: day(9), description: "Alquiler", amount: 210_000, transactionType: .expense, category: "Vivienda"),
            Movement(movementId: "salary:4", sourceId: 4, origin: "salary", transactionDate: day(18), description: "Salario quincenal", amount: 432_500, transactionType: .income, category: "Salario"),
        ]
    }
}
