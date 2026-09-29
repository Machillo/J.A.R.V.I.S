import Foundation

/// In-memory service with synthetic data for SwiftUI previews, UI tests and store/landing
/// screenshots. All names and amounts are invented (CLAUDE.md §4.F: no real data in fixtures).
///
/// It stores what the screens write so flows can be exercised end to end, but it does not
/// compute financial results: dashboard figures are fixed sample values, exactly like the
/// backend would return them. Write semantics follow the backend: a repeated idempotency key
/// is answered without a second row, and a missing movement is a 404.
public actor FixtureDincrService: DincrService {
    public enum Scenario: String, Sendable {
        /// `store`: the account of the store screenshots (StoreSample).
        case populated, empty, failing, newUser, legalRequired, choosePlan, store
    }

    private var profile: Profile
    private var rows: [Movement]
    private let scenario: Scenario
    private let latency: Duration
    private var nextID = 100
    private var seenKeys: Set<String> = []
    private var debtRows: [Debt]
    private var goalRows: [Goal]

    public init(scenario: Scenario = .populated, plan: PlanTier = .free, latency: Duration = .milliseconds(350), today: Date = .now,
                language: AppLanguage = .current) {
        self.scenario = scenario
        self.latency = latency
        self.profile = Profile(
            // Every field /auth/me always sends (auth/saas.py enrich_identity), same as Android.
            id: 4201, email: "ana@example.com", displayName: "Ana Solís", role: "user",
            planSelected: scenario != .newUser && scenario != .choosePlan,
            profileSetupCompleted: scenario != .newUser, baseCurrency: "CRC", numberFormat: "dot_comma", currencyPlacement: "before",
            subscription: .init(plan: plan.rawValue, status: "active"),
            legal: .init(required: scenario == .legalRequired, termsVersion: "2026-09", privacyVersion: "2026-09")
        )
        let populated = scenario == .populated
        self.rows = populated ? Self.sampleMovements(today: today) : []
        self.debtRows = populated ? [
            Debt(id: 31, name: "Tarjeta de crédito", debtType: "credit_card", totalAmount: 600_000, remainingAmount: 420_000, monthlyPayment: 45_000, interestRate: 36, paymentDay: 15, progressPercent: 30),
            Debt(id: 32, name: "Préstamo del carro", debtType: "loan", totalAmount: 2_400_000, remainingAmount: 820_000, monthlyPayment: 50_000, interestRate: 12, paymentDay: 1, progressPercent: 65.8),
        ] : []
        self.goalRows = populated ? [
            Goal(id: 41, name: "Fondo de emergencia", targetAmount: 1_500_000, currentAmount: 380_000, targetDate: "2027-06-30", priority: "high"),
            Goal(id: 42, name: "Viaje", targetAmount: 400_000, currentAmount: 90_000),
        ] : []
        if scenario == .store {
            profile = StoreSample.profile(plan: plan, language: language)
            rows = StoreSample.movements(language: language)
            debtRows = StoreSample.debts(language: language)
            goalRows = StoreSample.goals(language: language)
        }
    }

    public func me() async throws -> Profile {
        try await pause()
        return profile
    }

    public func completeProfileSetup(_ setup: ProfileSetup) async throws -> Profile {
        try await pause()
        profile = Profile(
            id: profile.id, email: profile.email, displayName: setup.displayName,
            planSelected: profile.planSelected, profileSetupCompleted: true, baseCurrency: setup.baseCurrency,
            numberFormat: setup.numberFormat, currencyPlacement: setup.currencyPlacement,
            subscription: profile.subscription, legal: profile.legal
        )
        return profile
    }

    public func acceptLegal(_ request: LegalAcceptRequest) async throws -> LegalAcceptResult {
        try await pause()
        guard request.termsVersion == profile.legal?.termsVersion, request.privacyVersion == profile.legal?.privacyVersion else {
            throw APIError(kind: .validation, status: 409, message: "Las versiones legales cambiaron.")
        }
        profile = profile.with(legal: .init(required: false, termsVersion: request.termsVersion, privacyVersion: request.privacyVersion, acceptedAt: "2026-09-28T12:00:00Z"))
        return LegalAcceptResult(status: "ok", required: false)
    }

    public func plans() async throws -> [PlanOption] {
        try await pause()
        return [
            PlanOption(code: "free", name: "Free", tagline: "Lo esencial para ordenar tu dinero.", features: ["Movimientos", "Deudas y metas"]),
            PlanOption(code: "basic", name: "Basic", tagline: "Presupuesto y calendario.", features: ["Presupuesto guiado", "Calendario financiero"], regularPriceCrc: 2_900),
            PlanOption(code: "vip", name: "VIP", tagline: "Estrategia y correo.", features: ["Estrategia VIP", "Monitor de correo"], regularPriceCrc: 5_900),
        ]
    }

    public func billingCatalog() async throws -> BillingCatalog {
        try await pause()
        return BillingCatalog(plans: nil, promotion: nil, notice: nil)
    }

    public func choosePlan(_ request: PlanChangeRequest) async throws -> PlanChangeResult {
        try await pause()
        // Without an active promotion the backend accepts only Free here; paid plans come from a store.
        guard request.plan == PlanTier.free.rawValue else {
            throw APIError(kind: .subscriptionRequired, status: 402, message: "Este plan se activa desde la tienda.")
        }
        profile = profile.with(planSelected: true, subscription: .init(plan: request.plan, status: "active"))
        return PlanChangeResult(status: "ok", plan: request.plan, pendingPlan: nil, effectiveAt: nil, message: nil, profile: profile)
    }

    public func featureFlags() async throws -> FeatureFlags {
        try await pause()
        return FeatureFlags(flags: OpsFlag.allCases.map { FeatureFlags.Flag(flagKey: $0.rawValue, enabled: true) })
    }

    public func deleteAccount() async throws {
        try await pause()
    }

    public func debts() async throws -> [Debt] {
        try await pause()
        return debtRows
    }

    public func payDebt(id: Int, amount: Decimal, idempotencyKey: String) async throws -> DebtPaymentResult {
        try await pause()
        try WriteContract.checkAmount(amount)
        guard let index = debtRows.firstIndex(where: { $0.id == id }) else {
            throw APIError(kind: .notFound, status: 404, message: "Deuda no encontrada.")
        }
        let old = debtRows[index]
        guard seenKeys.insert(idempotencyKey).inserted else {
            return DebtPaymentResult(status: "ok", debtId: id, paymentAmount: amount, newRemainingAmount: old.remainingAmount)
        }
        // Like the backend: a payment larger than the balance is capped at the balance.
        let remaining = max(0, (old.remainingAmount ?? 0) - amount)
        debtRows[index] = Debt(id: old.id, name: old.name, debtType: old.debtType, totalAmount: old.totalAmount, remainingAmount: remaining,
                               monthlyPayment: old.monthlyPayment, interestRate: old.interestRate, paymentDay: old.paymentDay,
                               nextPaymentDate: old.nextPaymentDate, progressPercent: old.progressPercent)
        return DebtPaymentResult(status: "ok", debtId: id, paymentAmount: min(amount, old.remainingAmount ?? amount), newRemainingAmount: remaining)
    }

    public func goals() async throws -> [Goal] {
        try await pause()
        return goalRows
    }

    public func contribute(goalID: Int, _ contribution: GoalContribution, idempotencyKey: String) async throws -> Goal {
        try await pause()
        try WriteContract.checkAmount(contribution.amount)
        guard let index = goalRows.firstIndex(where: { $0.id == goalID }) else {
            throw APIError(kind: .notFound, status: 404, message: "Meta no encontrada.")
        }
        guard seenKeys.insert(idempotencyKey).inserted else { return goalRows[index] }
        let old = goalRows[index]
        var current = (old.currentAmount ?? 0) + contribution.amount
        if let target = old.targetAmount { current = min(current, target) }
        goalRows[index] = Goal(id: old.id, name: old.name, targetAmount: old.targetAmount, currentAmount: current,
                               targetDate: old.targetDate, priority: old.priority, status: old.status)
        return goalRows[index]
    }

    public func freeDashboard() async throws -> FreeDashboard {
        try await pause()
        if scenario == .empty || scenario == .newUser {
            // The backend always returns six months, zero-filled.
            let months = ["2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09"]
            return FreeDashboard(month: "2026-09", income: 0, expenses: 0, debtPaid: 0, debtBalance: 0, balance: 0,
                                 availableAfterCommitments: 0, categories: [],
                                 monthlyHistory: months.map { MonthTotals(month: $0, income: 0, expenses: 0, debtPaid: 0, balance: 0) })
        }
        if scenario == .store { return StoreSample.dashboard(movements: rows, debts: debtRows) }
        return Self.sampleDashboard
    }

    public func movements() async throws -> [Movement] {
        try await pause()
        return rows.sorted { ($0.day ?? "") > ($1.day ?? "") }
    }

    public func create(_ kind: Movement.Kind, _ entry: EntryCreate, idempotencyKey: String) async throws {
        try await pause()
        guard seenKeys.insert(idempotencyKey).inserted else { return }
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
        guard rows.contains(where: { $0.movementId == movementID }) else {
            throw APIError(kind: .notFound, status: 404, message: "Movimiento no encontrado o no eliminable.")
        }
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
            // Cents and a category outside the editor's list: editing must keep both.
            Movement(movementId: "expense:12", sourceId: 12, origin: "expense", transactionDate: day(1), description: "Feria del agricultor", amount: Decimal(string: "12345.5")!, transactionType: .expense, category: "Feria"),
            Movement(movementId: "transaction:9", sourceId: 9, origin: "transaction", transactionDate: day(1), description: "Aviso bancario · Gasolinera", amount: 25_000, transactionType: .expense, category: "Gasolina", editable: false),
            Movement(movementId: "salary:8", sourceId: 8, origin: "salary", transactionDate: day(3), description: "Salario quincenal", amount: 432_500, transactionType: .income, category: "Salario"),
            Movement(movementId: "expense:7", sourceId: 7, origin: "expense", transactionDate: day(4), description: "Internet del hogar", amount: 24_900, transactionType: .expense, category: "Internet"),
            Movement(movementId: "expense:6", sourceId: 6, origin: "expense", transactionDate: day(6), description: "Farmacia", amount: 9_800, transactionType: .expense, category: "Salud"),
            Movement(movementId: "expense:5", sourceId: 5, origin: "expense", transactionDate: day(9), description: "Alquiler", amount: 210_000, transactionType: .expense, category: "Vivienda"),
            Movement(movementId: "salary:4", sourceId: 4, origin: "salary", transactionDate: day(18), description: "Salario quincenal", amount: 432_500, transactionType: .income, category: "Salario"),
        ]
    }
}
