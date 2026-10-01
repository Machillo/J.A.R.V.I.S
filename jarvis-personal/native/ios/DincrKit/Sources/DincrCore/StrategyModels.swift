import Foundation

// The Plan tab's strategy (Estrategia) and money distribution (Distribución de dinero). Three
// contracts, one per kind of account, all computed by the backend:
// - Basic: `GET /finance/strategy-basic` (`Strategy`, InsightModels.swift).
// - VIP Users: `GET /vip/strategy-dashboard`, `strategy.scope == "users"`.
// - Owner: `GET /jarvis/premium/strategy-dashboard`, `strategy.scope == "owner"` (the historical
//   JARVIS model). Only the server role in `/auth/me` selects it; the backend decides again.
// Decoding is tolerant: an unknown key is ignored and a value of an unexpected type is unknown
// (nil, shown as "—"), never zero. Android twin: `StrategyModels.kt`.

extension KeyedDecodingContainer {
    /// The value, or nil when it is missing, null or of another type: one odd field never hides the screen.
    func lenient<T: Decodable>(_ type: T.Type, _ key: Key) -> T? {
        // `try?` flattens the optional: a type mismatch and a null are both nil.
        try? decodeIfPresent(type, forKey: key)
    }
}

/// `GET /user-product/vip/strategy-dashboard` and `GET /jarvis/premium/strategy-dashboard`.
public struct StrategyDashboard: Decodable, Sendable, Equatable {
    public let status: String?
    public let userRole: String?
    public let title: String?
    public let content: String?
    public let strategy: DashboardStrategy?
    public let source: String?

    enum CodingKeys: String, CodingKey { case status, userRole, title, content, strategy, source }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        status = c.lenient(String.self, .status)
        userRole = c.lenient(String.self, .userRole)
        title = c.lenient(String.self, .title)
        content = c.lenient(String.self, .content)
        strategy = c.lenient(DashboardStrategy.self, .strategy)
        source = c.lenient(String.self, .source)
    }
}

/// The `strategy` object of the dashboard. Users and Owner share the fields; the Owner adds his
/// cycle, cash and statement figures. `distributableAccountCash` is always nil for Users (DINCR has
/// no account balance it can trust for them), and the app never shows a cash balance it lacks.
public struct DashboardStrategy: Decodable, Sendable, Equatable {
    public struct Priority: Decodable, Sendable, Equatable {
        public let kind: String?
        public let title: String?
        public let detail: String?
    }
    public struct IncomePolicy: Decodable, Sendable, Equatable {
        public let policy: String?
        public let source: String?

        enum CodingKeys: String, CodingKey { case policy, source }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            policy = c.lenient(String.self, .policy)
            source = c.lenient(String.self, .source)
        }
    }
    public struct EmergencyFund: Decodable, Sendable, Equatable {
        public let current: Decimal?
        public let monthlyBase: Decimal?
        public let nextTarget: Decimal?
        public let gapToNextTarget: Decimal?
        public let level: String?

        enum CodingKeys: String, CodingKey { case current, monthlyBase, nextTarget, gapToNextTarget, level }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            current = c.lenient(Decimal.self, .current)
            monthlyBase = c.lenient(Decimal.self, .monthlyBase)
            nextTarget = c.lenient(Decimal.self, .nextTarget)
            gapToNextTarget = c.lenient(Decimal.self, .gapToNextTarget)
            level = c.lenient(String.self, .level)
        }
    }
    public struct TimelineItem: Decodable, Sendable, Equatable {
        public let priority: Int?
        public let name: String?
        public let remainingAmount: Decimal?
        public let recommendedPayment: Decimal?
        public let estimatedPayoffDate: String?

        enum CodingKeys: String, CodingKey { case priority, name, remainingAmount, recommendedPayment, estimatedPayoffDate }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            priority = c.lenient(Int.self, .priority)
            name = c.lenient(String.self, .name)
            remainingAmount = c.lenient(Decimal.self, .remainingAmount)
            recommendedPayment = c.lenient(Decimal.self, .recommendedPayment)
            estimatedPayoffDate = c.lenient(String.self, .estimatedPayoffDate)
        }
    }
    /// One bucket of the distribution: `meta_prioritaria`, `ataque_de_deuda`, `fondo_de_emergencia`,
    /// `vida_controlada`, `inversion`, `metas_o_inversion`.
    public struct AllocationItem: Decodable, Sendable, Equatable {
        public let key: String?
        public let percentage: Double?
        public let amount: Decimal?
        public let targetName: String?

        enum CodingKeys: String, CodingKey { case key, percentage, amount, targetName }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            key = c.lenient(String.self, .key)
            percentage = c.lenient(Double.self, .percentage)
            amount = c.lenient(Decimal.self, .amount)
            targetName = c.lenient(String.self, .targetName)
        }
    }
    /// How the distributable amount was reached. Users and Owner send different keys; only the
    /// ones present are shown, in `DistributionFormula.order`.
    public struct DistributionFormula: Decodable, Sendable, Equatable {
        public let cashAvailableNow: Decimal?
        public let income: Decimal?
        public let recordedSpending: Decimal?
        public let statementSpending: Decimal?
        public let newSpendingAfterCut: Decimal?
        public let debtCommitment: Decimal?
        public let pendingRecurring: Decimal?
        public let mandatoryFixedPending: Decimal?
        public let surplus: Decimal?
        public let deficit: Decimal?

        enum CodingKeys: String, CodingKey {
            case cashAvailableNow, income, recordedSpending, statementSpending, newSpendingAfterCut
            case debtCommitment, pendingRecurring, mandatoryFixedPending, surplus, deficit
        }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            cashAvailableNow = c.lenient(Decimal.self, .cashAvailableNow)
            income = c.lenient(Decimal.self, .income)
            recordedSpending = c.lenient(Decimal.self, .recordedSpending)
            statementSpending = c.lenient(Decimal.self, .statementSpending)
            newSpendingAfterCut = c.lenient(Decimal.self, .newSpendingAfterCut)
            debtCommitment = c.lenient(Decimal.self, .debtCommitment)
            pendingRecurring = c.lenient(Decimal.self, .pendingRecurring)
            mandatoryFixedPending = c.lenient(Decimal.self, .mandatoryFixedPending)
            surplus = c.lenient(Decimal.self, .surplus)
            deficit = c.lenient(Decimal.self, .deficit)
        }

        /// The wire keys present, in reading order (Owner: cash first; both: surplus and deficit last).
        public var lines: [(key: String, amount: Decimal)] {
            let all: [(String, Decimal?)] = [
                ("cash_available_now", cashAvailableNow), ("income", income), ("recorded_spending", recordedSpending),
                ("statement_spending", statementSpending), ("new_spending_after_cut", newSpendingAfterCut),
                ("debt_commitment", debtCommitment), ("pending_recurring", pendingRecurring),
                ("mandatory_fixed_pending", mandatoryFixedPending), ("surplus", surplus), ("deficit", deficit),
            ]
            return all.compactMap { pair in pair.1.map { (key: pair.0, amount: $0) } }
        }
    }
    public struct PendingItem: Decodable, Sendable, Equatable {
        public let name: String?
        public let amount: Decimal?
        public let dueDay: Int?

        enum CodingKeys: String, CodingKey { case name, amount, dueDay, expectedAmount, pendingAmount }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            name = c.lenient(String.self, .name)
            amount = c.lenient(Decimal.self, .amount) ?? c.lenient(Decimal.self, .pendingAmount) ?? c.lenient(Decimal.self, .expectedAmount)
            dueDay = c.lenient(Int.self, .dueDay)
        }
    }
    public struct InvestmentPortfolio: Decodable, Sendable, Equatable {
        public let marketValue: Decimal?
        public let contributedCapital: Decimal?
        public let netPnl: Decimal?
        public let currency: String?

        enum CodingKeys: String, CodingKey { case marketValue, contributedCapital, netPnl, currency }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            marketValue = c.lenient(Decimal.self, .marketValue)
            contributedCapital = c.lenient(Decimal.self, .contributedCapital)
            netPnl = c.lenient(Decimal.self, .netPnl)
            currency = c.lenient(String.self, .currency)
        }
    }

    public let scope: String?
    public let status: String?
    public let title: String?
    public let objective: String?
    public let priority: Priority?
    public let monthlyIncome: Decimal?
    public let incomePolicy: IncomePolicy?
    public let monthlyExpenses: Decimal?
    public let debtCommitmentCurrentCycle: Decimal?
    public let pendingRecurringTotal: Decimal?
    public let safeToSpend: Decimal?
    public let emergencyFund: EmergencyFund?
    public let timeline: [TimelineItem]?
    public let estimatedDebtFreeDate: String?
    public let totalDebt: Decimal?
    public let debtProgressPercent: Double?
    public let investmentRecommended: Decimal?
    public let rules: [String]?
    public let allocationBaseAmount: Decimal?
    public let allocationItems: [AllocationItem]?
    public let distributionFormula: DistributionFormula?
    // Owner only (nil for Users).
    public let recurringMonthlyIncome: Decimal?
    public let currentMonthExtraNet: Decimal?
    public let incomeReceivedCurrentCycle: Decimal?
    public let remainingIncomeCurrentCycle: Decimal?
    public let distributableAccountCash: Decimal?
    public let statementExpenses: Decimal?
    public let newExpensesAfterCut: Decimal?
    public let mandatoryFixedPending: Decimal?
    public let mandatoryFixedPendingItems: [PendingItem]?
    public let investmentPortfolio: InvestmentPortfolio?
    public let baseTimeline: [TimelineItem]?
    public let monthsSavedByCurrentExtras: Int?

    enum CodingKeys: String, CodingKey {
        case scope, status, title, objective, priority, monthlyIncome, incomePolicy, monthlyExpenses
        case debtCommitmentCurrentCycle, pendingRecurringTotal, safeToSpend, emergencyFund, timeline
        case estimatedDebtFreeDate, totalDebt, debtProgressPercent, investmentRecommended, rules
        case allocationBaseAmount, allocationItems, distributionFormula
        case recurringMonthlyIncome, currentMonthExtraNet, incomeReceivedCurrentCycle, remainingIncomeCurrentCycle
        case distributableAccountCash, statementExpenses, newExpensesAfterCut, mandatoryFixedPending
        case mandatoryFixedPendingItems, investmentPortfolio, baseTimeline, monthsSavedByCurrentExtras
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        scope = c.lenient(String.self, .scope)
        status = c.lenient(String.self, .status)
        title = c.lenient(String.self, .title)
        objective = c.lenient(String.self, .objective)
        priority = c.lenient(Priority.self, .priority)
        monthlyIncome = c.lenient(Decimal.self, .monthlyIncome)
        incomePolicy = c.lenient(IncomePolicy.self, .incomePolicy)
        monthlyExpenses = c.lenient(Decimal.self, .monthlyExpenses)
        debtCommitmentCurrentCycle = c.lenient(Decimal.self, .debtCommitmentCurrentCycle)
        pendingRecurringTotal = c.lenient(Decimal.self, .pendingRecurringTotal)
        safeToSpend = c.lenient(Decimal.self, .safeToSpend)
        emergencyFund = c.lenient(EmergencyFund.self, .emergencyFund)
        timeline = c.lenient([TimelineItem].self, .timeline)
        estimatedDebtFreeDate = c.lenient(String.self, .estimatedDebtFreeDate)
        totalDebt = c.lenient(Decimal.self, .totalDebt)
        debtProgressPercent = c.lenient(Double.self, .debtProgressPercent)
        investmentRecommended = c.lenient(Decimal.self, .investmentRecommended)
        rules = c.lenient([String].self, .rules)
        allocationBaseAmount = c.lenient(Decimal.self, .allocationBaseAmount)
        allocationItems = c.lenient([AllocationItem].self, .allocationItems)
        distributionFormula = c.lenient(DistributionFormula.self, .distributionFormula)
        recurringMonthlyIncome = c.lenient(Decimal.self, .recurringMonthlyIncome)
        currentMonthExtraNet = c.lenient(Decimal.self, .currentMonthExtraNet)
        incomeReceivedCurrentCycle = c.lenient(Decimal.self, .incomeReceivedCurrentCycle)
        remainingIncomeCurrentCycle = c.lenient(Decimal.self, .remainingIncomeCurrentCycle)
        distributableAccountCash = c.lenient(Decimal.self, .distributableAccountCash)
        statementExpenses = c.lenient(Decimal.self, .statementExpenses)
        newExpensesAfterCut = c.lenient(Decimal.self, .newExpensesAfterCut)
        mandatoryFixedPending = c.lenient(Decimal.self, .mandatoryFixedPending)
        mandatoryFixedPendingItems = c.lenient([PendingItem].self, .mandatoryFixedPendingItems)
        investmentPortfolio = c.lenient(InvestmentPortfolio.self, .investmentPortfolio)
        baseTimeline = c.lenient([TimelineItem].self, .baseTimeline)
        monthsSavedByCurrentExtras = c.lenient(Int.self, .monthsSavedByCurrentExtras)
    }

    /// The historical JARVIS model, sent only to the server-resolved Owner.
    public var isOwnerScope: Bool { scope == "owner" }
    public var needsIncome: Bool { status == "needs_income" }
}

/// Which strategy contract an identity reads. The role comes from `/auth/me` only: the Owner reads
/// his JARVIS route (never `/finance/strategy-vip`), VIP Users the Users dashboard (paused with
/// `vip_intelligence`, when Basic's is used instead), Basic its own, Free none.
public enum StrategySource: String, Sendable, Equatable, CaseIterable {
    case basic, usersDashboard, ownerDashboard, unavailable

    public static func of(_ profile: Profile?, flags: FeatureFlags) -> StrategySource {
        guard let profile else { return .unavailable }
        if profile.isOwner { return .ownerDashboard }
        switch profile.planTier {
        case .vip: return flags.isEnabled(.vipIntelligence) ? .usersDashboard : .basic
        case .basic: return .basic
        case .free: return .unavailable
        }
    }
}

/// One strategy answer, whichever contract produced it. Estrategia and Distribución read the same one.
public enum PlanStrategy: Sendable, Equatable {
    case basic(Strategy)
    case dashboard(StrategyDashboard)

    public var needsIncome: Bool {
        switch self {
        case .basic(let strategy): strategy.needsIncome
        case .dashboard(let dashboard): dashboard.strategy?.needsIncome ?? false
        }
    }
}

/// Display names of the distribution buckets and formula lines (presentation only).
public enum DistributionLabels {
    public static func bucket(_ key: String?, targetName: String? = nil, language: AppLanguage = .current) -> String {
        switch key {
        case "meta_prioritaria": return language.pick("Meta prioritaria", "Priority goal")
        case "ataque_de_deuda":
            let base = language.pick("Ataque de deuda", "Debt attack")
            guard let targetName, !targetName.isEmpty else { return base }
            return "\(base) · \(targetName)"
        case "fondo_de_emergencia": return "Salvavidas"
        case "vida_controlada": return language.pick("Vida controlada", "Controlled living")
        case "inversion": return language.pick("Inversión", "Investment")
        case "metas_o_inversion": return language.pick("Metas o inversión", "Goals or investment")
        default: return key ?? "—"
        }
    }

    public static func formula(_ key: String, language: AppLanguage = .current) -> String {
        switch key {
        case "cash_available_now": return language.pick("Efectivo disponible ahora", "Cash available now")
        case "income": return language.pick("Ingreso", "Income")
        case "recorded_spending": return language.pick("Gastos registrados", "Recorded spending")
        case "statement_spending": return language.pick("Gastos del estado de cuenta", "Statement spending")
        case "new_spending_after_cut": return language.pick("Gastos nuevos después del corte", "New spending after the cut")
        case "debt_commitment": return language.pick("Cuotas de deuda pendientes", "Pending debt payments")
        case "pending_recurring": return language.pick("Pagos recurrentes pendientes", "Pending recurring payments")
        case "mandatory_fixed_pending": return language.pick("Gastos fijos pendientes", "Pending fixed expenses")
        case "surplus": return language.pick("Sobrante para repartir", "Surplus to allocate")
        case "deficit": return language.pick("Faltante", "Shortfall")
        default: return key
        }
    }
}

/// Where the monthly income of a strategy comes from (`income_policy.source` of the shared income
/// policy, or strategy-basic's `income_source`): declared, or estimated from recorded income.
public enum IncomeSourceLabel {
    /// Copy shown whenever the income is an estimate, not what the user declared.
    public static func observedNote(_ language: AppLanguage = .current) -> String {
        language.pick("Estimado con tus ingresos registrados (no declarado)", "Estimated from your recorded income (not declared)")
    }

    public static func label(_ source: String?, language: AppLanguage = .current) -> String? {
        switch source {
        case "declared"?: return language.pick("Ingreso declarado", "Declared income")
        case "declared_capped_by_recorded"?: return language.pick("Declarado, ajustado a lo que registraste", "Declared, capped by what you recorded")
        case "recorded"?, "observed"?: return observedNote(language)
        case "none"?: return language.pick("Sin ingreso registrado", "No recorded income")
        default: return nil
        }
    }
}
