import Foundation

// Salvavidas (VIP; the Owner by role): `GET/PUT /user-product/vip/salvavidas`. The backend builds
// it and picks the model from the server role:
// - Users (`scope == "users"`): months of the workspace's own obligations (active debts' payments
//   and recurring expense items). The fund is the savings declared in the financial situation;
//   unknown savings stay unknown (`current_amount: null`), never "0 months". PUT: `target_months`
//   and/or `current_amount` (it updates the declared savings, the same field as the financial
//   situation; 422 without a situation). Never `protected_expense_ids`.
// - Owner (`scope == "owner"`): the historical JARVIS model (protected expenses, a manual balance).
//   PUT: `current_amount`, `protected_expense_ids` or `target_months`.
// The app never computes coverage on the device. Android twin: `SalvavidasModels.kt`.

public struct Salvavidas: Decodable, Sendable, Equatable {
    public struct Components: Decodable, Sendable, Equatable {
        public let debtMonthlyPayments: Decimal?
        public let recurringObligations: Decimal?
        public let mandatoryFixedExpenses: Decimal?
        public let protectedExpenses: Decimal?

        enum CodingKeys: String, CodingKey { case debtMonthlyPayments, recurringObligations, mandatoryFixedExpenses, protectedExpenses }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            debtMonthlyPayments = c.lenient(Decimal.self, .debtMonthlyPayments)
            recurringObligations = c.lenient(Decimal.self, .recurringObligations)
            mandatoryFixedExpenses = c.lenient(Decimal.self, .mandatoryFixedExpenses)
            protectedExpenses = c.lenient(Decimal.self, .protectedExpenses)
        }
    }
    /// A debt, a recurring obligation or (Owner) a fixed expense, with its monthly amount.
    public struct Line: Decodable, Sendable, Equatable, Identifiable {
        public let lineId: Int?
        public let name: String?
        public let monthlyAmount: Decimal?
        public let frequency: String?
        public let dueDay: Int?
        public let selected: Bool?

        public var id: String { "\(lineId ?? -1)-\(name ?? "")" }

        enum CodingKeys: String, CodingKey { case id, name, monthlyAmount, monthlyPayment, frequency, dueDay, paymentDay, selected }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            lineId = c.lenient(Int.self, .id)
            name = c.lenient(String.self, .name)
            // Debts carry `monthly_payment`; obligations and expenses `monthly_amount`.
            monthlyAmount = c.lenient(Decimal.self, .monthlyAmount) ?? c.lenient(Decimal.self, .monthlyPayment)
            frequency = c.lenient(String.self, .frequency)
            dueDay = c.lenient(Int.self, .dueDay) ?? c.lenient(Int.self, .paymentDay)
            selected = c.lenient(Bool.self, .selected)
        }
    }
    public struct Milestone: Decodable, Sendable, Equatable {
        public let months: Int?
        public let target: Decimal?
        public let reached: Bool?

        enum CodingKeys: String, CodingKey { case months, target, reached }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            months = c.lenient(Int.self, .months)
            target = c.lenient(Decimal.self, .target)
            reached = c.lenient(Bool.self, .reached)
        }
    }
    public struct Verification: Decodable, Sendable, Equatable {
        public let mode: String?
        public let message: String?
        public let accountLinked: Bool?

        enum CodingKeys: String, CodingKey { case mode, message, accountLinked }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            mode = c.lenient(String.self, .mode)
            message = c.lenient(String.self, .message)
            accountLinked = c.lenient(Bool.self, .accountLinked)
        }
    }

    /// The months a target may be set to, when the backend does not list them.
    public static let defaultTargetMonths = [1, 3, 6]

    public let status: String?
    public let scope: String?
    public let currentAmount: Decimal?
    public let currentAmountKnown: Bool?
    public let monthlyBase: Decimal?
    public let targetMonths: Int?
    public let allowedTargetMonths: [Int]?
    public let targetAmount: Decimal?
    public let missingAmount: Decimal?
    public let coverageMonths: Double?
    public let progressPercent: Double?
    public let components: Components?
    public let debts: [Line]?
    /// Users: the active recurring expense items.
    public let obligations: [Line]?
    public let milestones: [Milestone]?
    public let verification: Verification?
    // Owner only.
    public let protectedExpenseIds: [Int]?
    public let mandatoryExpenses: [Line]?
    public let availableExpenses: [Line]?
    public let excludedDebtDuplicates: [Line]?

    enum CodingKeys: String, CodingKey {
        case status, scope, currentAmount, currentAmountKnown, monthlyBase, targetMonths, allowedTargetMonths
        case targetAmount, missingAmount, coverageMonths, progressPercent, components, debts, obligations
        case milestones, verification, protectedExpenseIds, mandatoryExpenses, availableExpenses, excludedDebtDuplicates
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        status = c.lenient(String.self, .status)
        scope = c.lenient(String.self, .scope)
        currentAmount = c.lenient(Decimal.self, .currentAmount)
        currentAmountKnown = c.lenient(Bool.self, .currentAmountKnown)
        monthlyBase = c.lenient(Decimal.self, .monthlyBase)
        targetMonths = c.lenient(Int.self, .targetMonths)
        allowedTargetMonths = c.lenient([Int].self, .allowedTargetMonths)
        targetAmount = c.lenient(Decimal.self, .targetAmount)
        missingAmount = c.lenient(Decimal.self, .missingAmount)
        coverageMonths = c.lenient(Double.self, .coverageMonths)
        progressPercent = c.lenient(Double.self, .progressPercent)
        components = c.lenient(Components.self, .components)
        debts = c.lenient([Line].self, .debts)
        obligations = c.lenient([Line].self, .obligations)
        milestones = c.lenient([Milestone].self, .milestones)
        verification = c.lenient(Verification.self, .verification)
        protectedExpenseIds = c.lenient([Int].self, .protectedExpenseIds)
        mandatoryExpenses = c.lenient([Line].self, .mandatoryExpenses)
        availableExpenses = c.lenient([Line].self, .availableExpenses)
        excludedDebtDuplicates = c.lenient([Line].self, .excludedDebtDuplicates)
    }

    /// The historical JARVIS model, sent only to the server-resolved Owner.
    public var isOwnerScope: Bool { scope == "owner" }
    /// Users without debts or recurring obligations: there is nothing to cover yet.
    public var needsObligations: Bool { status == "needs_obligations" }

    /// Whether the fund's balance is known. Users: only what they declared (`current_amount_known`);
    /// a missing flag with a null amount is unknown too. Never inferred from zero.
    public var savingsKnown: Bool {
        guard currentAmount != nil else { return false }
        return isOwnerScope || currentAmountKnown != false
    }

    /// The target choices to offer, as the backend allows them.
    public var targetChoices: [Int] { (allowedTargetMonths?.isEmpty == false ? allowedTargetMonths : nil) ?? Self.defaultTargetMonths }

    /// "4.5 meses" when the backend sent a coverage for a known fund; "Sin dato" otherwise (never "0 meses").
    public func coverageLabel(language: AppLanguage = .current) -> String {
        guard savingsKnown, let months = coverageMonths else { return language.pick("Sin dato", "No data") }
        let text = String(format: "%.1f", months)
        let local = language == .spanish ? text.replacingOccurrences(of: ".", with: ",") : text
        return language.pick("\(local) meses", "\(local) months")
    }
}

/// Body of `PUT /vip/salvavidas`: exactly one change per request; absent fields are not sent.
public struct SalvavidasUpdate: Encodable, Sendable, Equatable {
    public let targetMonths: Int?
    public let currentAmount: Decimal?
    public let protectedExpenseIds: [Int]?

    private init(targetMonths: Int?, currentAmount: Decimal?, protectedExpenseIds: [Int]?) {
        self.targetMonths = targetMonths; self.currentAmount = currentAmount; self.protectedExpenseIds = protectedExpenseIds
    }

    /// Users and Owner: the 1/3/6-month goal.
    public static func target(months: Int) -> SalvavidasUpdate { SalvavidasUpdate(targetMonths: months, currentAmount: nil, protectedExpenseIds: nil) }
    /// The fund's balance. Owner: his manual balance. Users: their declared savings (the same field as
    /// the financial situation; the backend answers 422 when they have no situation yet).
    public static func currentAmount(_ amount: Decimal) -> SalvavidasUpdate { SalvavidasUpdate(targetMonths: nil, currentAmount: amount, protectedExpenseIds: nil) }
    /// Owner only: the optional fixed expenses the fund protects.
    public static func protectedExpenses(_ ids: [Int]) -> SalvavidasUpdate { SalvavidasUpdate(targetMonths: nil, currentAmount: nil, protectedExpenseIds: ids.sorted()) }

    enum CodingKeys: String, CodingKey { case targetMonths, currentAmount, protectedExpenseIds }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(targetMonths, forKey: .targetMonths)
        try c.encodeIfPresent(currentAmount, forKey: .currentAmount)
        try c.encodeIfPresent(protectedExpenseIds, forKey: .protectedExpenseIds)
    }
}
