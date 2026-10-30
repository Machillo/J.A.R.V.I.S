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
// Both scopes: `auto_contribution` (the automatic-contribution plan, also when disabled) and
// `declared_amount` (the balance last declared); with an enabled plan `current_amount` already
// includes the contributions (and, for the Owner, the estimated interest at `annual_interest_rate`).
// The app never computes coverage or contributions on the device. Android twin: `Salvavidas.kt`.

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
    /// Users: where the balance comes from (`declared`, `previous_salvavidas_save`) or nil.
    public let currentAmountSource: String?
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
    /// The balance last declared, before automatic contributions (null while unknown, Users).
    public let declaredAmount: Decimal?
    /// The automatic-contribution plan and what it added, or nil when none was ever saved.
    public let autoContribution: SalvavidasAutoContribution?
    // Owner only.
    /// Percent per year the Owner's Salvavidas earns (estimated interest). Never sent to Users.
    public let annualInterestRate: Decimal?
    public let protectedExpenseIds: [Int]?
    public let mandatoryExpenses: [Line]?
    public let availableExpenses: [Line]?
    public let excludedDebtDuplicates: [Line]?

    enum CodingKeys: String, CodingKey {
        case status, scope, currentAmount, currentAmountKnown, currentAmountSource, monthlyBase, targetMonths, allowedTargetMonths
        case targetAmount, missingAmount, coverageMonths, progressPercent, components, debts, obligations
        case milestones, verification, protectedExpenseIds, mandatoryExpenses, availableExpenses, excludedDebtDuplicates
        case declaredAmount, autoContribution, annualInterestRate
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        status = c.lenient(String.self, .status)
        scope = c.lenient(String.self, .scope)
        currentAmount = c.lenient(Decimal.self, .currentAmount)
        currentAmountKnown = c.lenient(Bool.self, .currentAmountKnown)
        currentAmountSource = c.lenient(String.self, .currentAmountSource)
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
        declaredAmount = c.lenient(Decimal.self, .declaredAmount)
        autoContribution = c.lenient(SalvavidasAutoContribution.self, .autoContribution)
        annualInterestRate = c.lenient(Decimal.self, .annualInterestRate)
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

    /// The enabled plan whose contributions the balance already includes, or nil.
    public var activePlan: SalvavidasAutoContribution? { autoContribution?.isEnabled == true ? autoContribution : nil }
    /// The annual interest rate field is the Owner's alone (the backend refuses it for anyone else).
    public var offersInterestRate: Bool { isOwnerScope }

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

/// The automatic-contribution plan as the backend answers it (`auto_contribution`): its settings
/// and, when enabled, what it added since `base_date` (estimates following the plan).
public struct SalvavidasAutoContribution: Decodable, Sendable, Equatable {
    public static let frequencies = ["weekly", "biweekly", "monthly"]

    public let enabled: Bool?
    public let amount: Decimal?
    public let frequency: String?
    public let startDate: String?
    public let endDate: String?
    public let baseAmount: Decimal?
    public let baseDate: String?
    public let contributionsCount: Int?
    public let contributionsAmount: Decimal?
    public let estimatedInterest: Decimal?
    public let nextDate: String?
    public let total: Decimal?

    enum CodingKeys: String, CodingKey {
        case enabled, amount, frequency, startDate, endDate, baseAmount, baseDate
        case contributionsCount, contributionsAmount, estimatedInterest, nextDate, total
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        enabled = c.lenient(Bool.self, .enabled)
        amount = c.lenient(Decimal.self, .amount)
        frequency = c.lenient(String.self, .frequency)
        startDate = c.lenient(String.self, .startDate)
        endDate = c.lenient(String.self, .endDate)
        baseAmount = c.lenient(Decimal.self, .baseAmount)
        baseDate = c.lenient(String.self, .baseDate)
        contributionsCount = c.lenient(Int.self, .contributionsCount)
        contributionsAmount = c.lenient(Decimal.self, .contributionsAmount)
        estimatedInterest = c.lenient(Decimal.self, .estimatedInterest)
        nextDate = c.lenient(String.self, .nextDate)
        total = c.lenient(Decimal.self, .total)
    }

    public var isEnabled: Bool { enabled == true }

    /// "Semanal" / "Quincenal" / "Mensual".
    public static func frequencyLabel(_ frequency: String?, language: AppLanguage = .current) -> String {
        switch frequency {
        case "weekly": return language.pick("Semanal", "Weekly")
        case "biweekly": return language.pick("Quincenal", "Every two weeks")
        case "monthly": return language.pick("Mensual", "Monthly")
        default: return "—"
        }
    }

    /// "3 aportes automáticos" / "1 automatic contribution".
    public static func countLabel(_ count: Int, language: AppLanguage = .current) -> String {
        count == 1 ? language.pick("1 aporte automático", "1 automatic contribution")
            : language.pick("\(count) aportes automáticos", "\(count) automatic contributions")
    }

    /// The one-line summary of a saved plan: "₡2.500 cada semana" / "₡2,500 every week".
    public static func summary(amount: String, frequency: String?, language: AppLanguage = .current) -> String {
        switch frequency {
        case "weekly": return language.pick("\(amount) cada semana", "\(amount) every week")
        case "biweekly": return language.pick("\(amount) cada quincena", "\(amount) every two weeks")
        case "monthly": return language.pick("\(amount) cada mes", "\(amount) every month")
        default: return amount
        }
    }

    /// "2,5 %" / "2.5%": the Owner's annual rate as typed back, with the language's decimal mark.
    public static func rateLabel(_ rate: Decimal, language: AppLanguage = .current) -> String {
        let text = "\(rate)"
        return language == .spanish ? text.replacingOccurrences(of: ".", with: ",") + " %" : text + "%"
    }
}

/// The plan the app sends in `auto_contribution`; the backend validates it again.
public struct SalvavidasPlanRequest: Encodable, Sendable, Equatable {
    /// The backend's cap for one contribution.
    public static let maxAmount = Decimal(string: "999999999.99")!

    public let enabled: Bool
    public let amount: Decimal
    public let frequency: String
    public let startDate: String
    /// nil: no end. Always sent (as null) so an edit can remove the end date.
    public let endDate: String?

    public init(enabled: Bool, amount: Decimal, frequency: String, startDate: String, endDate: String?) {
        self.enabled = enabled; self.amount = amount; self.frequency = frequency; self.startDate = startDate; self.endDate = endDate
    }

    enum CodingKeys: String, CodingKey { case enabled, amount, frequency, startDate, endDate }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(enabled, forKey: .enabled)
        try c.encode(amount, forKey: .amount)
        try c.encode(frequency, forKey: .frequency)
        try c.encode(startDate, forKey: .startDate)
        if let endDate { try c.encode(endDate, forKey: .endDate) } else { try c.encodeNil(forKey: .endDate) }
    }

    /// Refuses, before sending, what the backend would refuse.
    public func check() throws {
        try WriteContract.checkAmount(amount)
        guard amount <= Self.maxAmount, SalvavidasAutoContribution.frequencies.contains(frequency) else { throw WriteContract.invalid }
        try WriteContract.checkDate(startDate)
        guard startDate.count == 10 else { throw WriteContract.invalid }
        if let endDate {
            try WriteContract.checkDate(endDate)
            guard endDate.count == 10, endDate >= startDate else {
                throw APIError(kind: .validation, message: AppLanguage.current.pick(
                    "La fecha final debe ser después del primer aporte.", "The end date must be after the first contribution."))
            }
        }
    }
}

/// The Owner's annual interest rate typed as a percent ("2,5" or "2.5"): 0–50, at most 4 decimals.
public enum SalvavidasRateInput {
    public static let maxRate = Decimal(50)

    public static func parse(_ text: String) -> Decimal? {
        let trimmed = text.replacingOccurrences(of: " ", with: "").replacingOccurrences(of: "%", with: "")
        guard !trimmed.isEmpty, trimmed.allSatisfy({ $0.isASCII && ($0.isNumber || $0 == "." || $0 == ",") }) else { return nil }
        let parts = trimmed.replacingOccurrences(of: ",", with: ".").split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count <= 2, !parts[0].isEmpty, parts.count == 1 || (1...4).contains(parts[1].count) else { return nil }
        guard let value = Decimal(string: parts.joined(separator: "."), locale: Locale(identifier: "en_US_POSIX")),
              value >= 0, value <= maxRate else { return nil }
        return value
    }
}

/// Body of `PUT /vip/salvavidas`; absent fields are not sent. The goal, the balance and the
/// protected expenses go one per request; the automatic-contribution plan may carry the balance
/// (required while the user's savings are unknown) and, for the Owner, the interest rate.
public struct SalvavidasUpdate: Encodable, Sendable, Equatable {
    public let targetMonths: Int?
    public let currentAmount: Decimal?
    public let protectedExpenseIds: [Int]?
    public let autoContribution: SalvavidasPlanRequest?
    /// Owner only: percent per year (the backend answers 422 to anyone else).
    public let annualInterestRate: Decimal?

    private init(targetMonths: Int? = nil, currentAmount: Decimal? = nil, protectedExpenseIds: [Int]? = nil,
                 autoContribution: SalvavidasPlanRequest? = nil, annualInterestRate: Decimal? = nil) {
        self.targetMonths = targetMonths; self.currentAmount = currentAmount; self.protectedExpenseIds = protectedExpenseIds
        self.autoContribution = autoContribution; self.annualInterestRate = annualInterestRate
    }

    /// Users and Owner: the 1/3/6-month goal.
    public static func target(months: Int) -> SalvavidasUpdate { SalvavidasUpdate(targetMonths: months) }
    /// The fund's balance. Owner: his manual balance. Users: their declared savings (the same field as
    /// the financial situation; the backend answers 422 when they have no situation yet).
    public static func currentAmount(_ amount: Decimal) -> SalvavidasUpdate { SalvavidasUpdate(currentAmount: amount) }
    /// Owner only: the optional fixed expenses the fund protects.
    public static func protectedExpenses(_ ids: [Int]) -> SalvavidasUpdate { SalvavidasUpdate(protectedExpenseIds: ids.sorted()) }
    /// The automatic-contribution plan (nil keeps the saved one), with the balance declared today
    /// when the savings are unknown, and the Owner's rate. nil when there is nothing to send.
    public static func plan(_ plan: SalvavidasPlanRequest?, currentAmount: Decimal? = nil, annualInterestRate: Decimal? = nil) -> SalvavidasUpdate? {
        guard plan != nil || currentAmount != nil || annualInterestRate != nil else { return nil }
        return SalvavidasUpdate(currentAmount: currentAmount, autoContribution: plan, annualInterestRate: annualInterestRate)
    }

    var isEmpty: Bool {
        targetMonths == nil && currentAmount == nil && protectedExpenseIds == nil && autoContribution == nil && annualInterestRate == nil
    }

    enum CodingKeys: String, CodingKey { case targetMonths, currentAmount, protectedExpenseIds, autoContribution, annualInterestRate }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encodeIfPresent(targetMonths, forKey: .targetMonths)
        try c.encodeIfPresent(currentAmount, forKey: .currentAmount)
        try c.encodeIfPresent(protectedExpenseIds, forKey: .protectedExpenseIds)
        try c.encodeIfPresent(autoContribution, forKey: .autoContribution)
        try c.encodeIfPresent(annualInterestRate, forKey: .annualInterestRate)
    }
}
