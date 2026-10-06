import Foundation

// Debts and goals: the Plan tab. Same shapes as Android `PlanningModels.kt`. The backend owns
// every balance; the app sends only what the user typed and shows what the server answers.

/// A row of `GET /user-product/finance/debts`.
public struct Debt: Decodable, Sendable, Equatable, Identifiable {
    public let id: Int
    public let name: String?
    public let debtType: String?
    public let totalAmount: Decimal?
    public let remainingAmount: Decimal?
    public let monthlyPayment: Decimal?
    public let interestRate: Decimal?
    public let paymentDay: Int?
    public let nextPaymentDate: String?
    public let progressPercent: Double?
    /// Whether DINCR knows the rate (the server's rule): false for a rate never given and for an
    /// unconfirmed historical 0. Nil from an older server (the stored rate is then shown as before).
    public let interestRateKnown: Bool?

    public init(id: Int, name: String?, debtType: String? = "other", totalAmount: Decimal? = nil, remainingAmount: Decimal?,
                monthlyPayment: Decimal? = nil, interestRate: Decimal? = nil, paymentDay: Int? = nil,
                nextPaymentDate: String? = nil, progressPercent: Double? = nil, interestRateKnown: Bool? = nil) {
        self.id = id; self.name = name; self.debtType = debtType; self.totalAmount = totalAmount
        self.remainingAmount = remainingAmount; self.monthlyPayment = monthlyPayment; self.interestRate = interestRate
        self.paymentDay = paymentDay; self.nextPaymentDate = nextPaymentDate; self.progressPercent = progressPercent
        self.interestRateKnown = interestRateKnown
    }

    /// The rate the edit form starts with: an unknown rate starts empty, never as "0" (UNKNOWN ≠ 0%).
    /// Android: `Debt.rateForEditing`.
    public var rateForEditing: Decimal? { interestRateKnown == false ? nil : interestRate }

    /// The backend's paid percentage, only when it can be true: the list answers 0 % when the
    /// original amount is unknown (`ELSE 0`), which is not a fact about the debt. Unknown ≠ 0 %.
    /// Android: `Debt.knownProgressPercent`.
    public var knownProgressPercent: Double? {
        guard let totalAmount, totalAmount > 0 else { return nil }
        return progressPercent
    }
}

/// `POST /finance/debts/{id}/payments`.
public struct AmountRequest: Encodable, Sendable, Equatable {
    public let amount: Decimal
}

public struct DebtPaymentResult: Decodable, Sendable, Equatable {
    public let status: String?
    public let debtId: Int?
    public let paymentAmount: Decimal?
    public let newRemainingAmount: Decimal?

    public init(status: String?, debtId: Int?, paymentAmount: Decimal?, newRemainingAmount: Decimal?) {
        self.status = status; self.debtId = debtId; self.paymentAmount = paymentAmount; self.newRemainingAmount = newRemainingAmount
    }
}

/// A row of `GET /user-product/goals`.
public struct Goal: Decodable, Sendable, Equatable, Identifiable {
    public let id: Int
    public let name: String?
    public let targetAmount: Decimal?
    public let currentAmount: Decimal?
    public let targetDate: String?
    public let priority: String?
    public let status: String?

    public init(id: Int, name: String?, targetAmount: Decimal?, currentAmount: Decimal?, targetDate: String? = nil, priority: String? = "medium", status: String? = "active") {
        self.id = id; self.name = name; self.targetAmount = targetAmount; self.currentAmount = currentAmount
        self.targetDate = targetDate; self.priority = priority; self.status = status
    }

    /// What is left to reach the target; never negative. Nil when the target is unknown.
    public var remaining: Decimal? {
        guard let targetAmount else { return nil }
        return max(0, targetAmount - (currentAmount ?? 0))
    }
}

/// `POST /goals/{id}/contributions`.
public struct GoalContribution: Encodable, Sendable, Equatable {
    public let amount: Decimal
    public let contributionDate: String?

    public init(amount: Decimal, contributionDate: String?) {
        self.amount = amount; self.contributionDate = contributionDate
    }
}

/// Client-side guard for money a write sends: the same bounds as `AmountInput` (positive, at most
/// two decimals, NUMERIC(12,2)). The screens already parse with `AmountInput`; this refuses a value
/// that reached the service any other way instead of sending it.
public enum WriteContract {
    public static var invalid: APIError {
        APIError(kind: .validation, message: AppLanguage.current.pick("Revisá los datos e intentá nuevamente.", "Check the information and try again."))
    }

    static func decimals(_ value: Decimal, fit places: Int) -> Bool {
        var copy = value
        var rounded = Decimal()
        NSDecimalRound(&rounded, &copy, places, .plain)
        return rounded == value
    }

    /// Positive (or zero when `allowZero`), at most 2 decimals, at most 9,999,999,999.99.
    public static func checkAmount(_ amount: Decimal, allowZero: Bool = false) throws {
        guard allowZero ? amount >= 0 : amount > 0, amount <= AmountInput.maxAmount, decimals(amount, fit: AmountInput.maxFractionDigits) else {
            throw APIError(kind: .validation, message: AppLanguage.current.pick(
                "El monto no es válido.", "The amount is not valid."))
        }
    }

    /// The user's own exchange rate: > 0, <= 100 000, at most 6 decimals (`exchange_rate` NUMERIC(14,6)).
    public static func checkRate(_ rate: Decimal) throws {
        guard rate > 0, rate <= RateInput.maxRate, decimals(rate, fit: RateInput.maxFractionDigits) else {
            throw APIError(kind: .validation, message: AppLanguage.current.pick("El tipo de cambio no es válido.", "The exchange rate is not valid."))
        }
    }

    static func checkName(_ name: String) throws {
        let trimmed = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, trimmed.count <= 120 else { throw invalid }
    }

    public static func check(_ request: DebtRequest) throws {
        try checkName(request.name)
        try checkAmount(request.remainingAmount, allowZero: true)
        if let total = request.totalAmount { try checkAmount(total) }
        if let monthly = request.monthlyPayment { try checkAmount(monthly, allowZero: true) }
        if let rate = request.interestRate { guard rate >= 0, rate <= 999, decimals(rate, fit: 4) else { throw invalid } }
        if let day = request.paymentDay { guard (1...31).contains(day) else { throw invalid } }
    }

    public static func check(_ request: GoalRequest) throws {
        try checkName(request.name)
        try checkAmount(request.targetAmount)
        try checkAmount(request.currentAmount, allowZero: true)
        try checkDate(request.targetDate)
        guard GoalRequest.priorities.contains(request.priority) else { throw invalid }
    }

    public static func check(_ request: SavingsPlanRequest) throws {
        try checkName(request.name)
        try checkAmount(request.monthlyAmount)
        try checkAmount(request.savedAmount, allowZero: true)
        try checkDate(request.startDate)
        try checkDate(request.endDate)
        guard request.startDate <= request.endDate else { throw invalid }
    }

    public static func check(_ profile: FinancialProfile) throws {
        for amount in [profile.fixedMonthlySalary, profile.hourlyRate, profile.essentialMonthlyExpenses, profile.liquidSavings,
                       profile.emergencyFundTarget, profile.discretionaryMonthlyMinimum].compactMap({ $0 }) {
            try checkAmount(amount, allowZero: true)
        }
        if let days = profile.workDaysPerWeek { guard (1...7).contains(days) else { throw invalid } }
        if let hours = profile.hoursPerDay { guard hours > 0, hours <= 24, decimals(hours, fit: 2) else { throw invalid } }
    }

    /// `YYYY-MM-DD` of a real calendar day, or the write is refused.
    public static func checkDate(_ day: String?) throws {
        guard let day else { return }
        let formatter = DateFormatter()
        formatter.calendar = Calendar(identifier: .gregorian)
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "yyyy-MM-dd"
        guard day.count == 10, let date = formatter.date(from: day), formatter.string(from: date) == day else {
            throw APIError(kind: .validation, message: AppLanguage.current.pick("La fecha no es válida.", "The date is not valid."))
        }
    }
}

/// Body of `POST /finance/debts` and `PUT /finance/debts/{id}` (editing needs Basic).
public struct DebtRequest: Encodable, Sendable, Equatable {
    public let name: String
    public let debtType: String
    public let remainingAmount: Decimal
    public let totalAmount: Decimal?
    public let monthlyPayment: Decimal?
    public let interestRate: Decimal?
    public let paymentDay: Int?
    /// On edit: true only when the user typed or changed the rate. Saving the rest of the debt never
    /// confirms the rate it was loaded with (the server keeps an unconfirmed rate unconfirmed).
    public let interestRateConfirmed: Bool?

    public init(name: String, debtType: String = "other", remainingAmount: Decimal, totalAmount: Decimal?, monthlyPayment: Decimal?,
                interestRate: Decimal? = nil, paymentDay: Int? = nil, interestRateConfirmed: Bool? = nil) {
        self.name = name; self.debtType = debtType; self.remainingAmount = remainingAmount; self.totalAmount = totalAmount
        self.monthlyPayment = monthlyPayment; self.interestRate = interestRate; self.paymentDay = paymentDay
        self.interestRateConfirmed = interestRateConfirmed
    }

    /// Whether an edit touched the rate: its text differs from the one the form started with.
    public static func rateConfirmed(initial: String, current: String) -> Bool {
        initial.trimmingCharacters(in: .whitespaces) != current.trimmingCharacters(in: .whitespaces)
    }
}

/// Body of `POST /goals` and `PUT /goals/{id}` (`status` only on edit, which needs Basic).
public struct GoalRequest: Encodable, Sendable, Equatable {
    public static let priorities = ["high", "medium", "low"]
    public let name: String
    public let targetAmount: Decimal
    public let currentAmount: Decimal
    public let targetDate: String?
    public let priority: String
    public let status: String?

    public init(name: String, targetAmount: Decimal, currentAmount: Decimal, targetDate: String?, priority: String = "medium", status: String? = nil) {
        self.name = name; self.targetAmount = targetAmount; self.currentAmount = currentAmount
        self.targetDate = targetDate; self.priority = priority; self.status = status
    }
}

/// A row of `GET /user-product/savings-plans`.
public struct SavingsPlan: Decodable, Sendable, Equatable, Identifiable {
    public let id: Int
    public let name: String?
    public let monthlyAmount: Decimal?
    public let savedAmount: Decimal?
    public let startDate: String?
    public let endDate: String?
    public let status: String?

    public init(id: Int, name: String?, monthlyAmount: Decimal?, savedAmount: Decimal?, startDate: String? = nil, endDate: String? = nil, status: String? = "active") {
        self.id = id; self.name = name; self.monthlyAmount = monthlyAmount; self.savedAmount = savedAmount
        self.startDate = startDate; self.endDate = endDate; self.status = status
    }
}

public struct SavingsPlanRequest: Encodable, Sendable, Equatable {
    public let name: String
    public let monthlyAmount: Decimal
    public let savedAmount: Decimal
    public let startDate: String
    public let endDate: String
    public let status: String?

    public init(name: String, monthlyAmount: Decimal, savedAmount: Decimal, startDate: String, endDate: String, status: String? = nil) {
        self.name = name; self.monthlyAmount = monthlyAmount; self.savedAmount = savedAmount
        self.startDate = startDate; self.endDate = endDate; self.status = status
    }
}

/// `GET /user-product/basic/budget` (Basic).
public struct Budget: Decodable, Sendable, Equatable {
    public struct Item: Decodable, Sendable, Equatable, Identifiable {
        public let category: String
        public let monthlyLimit: Decimal?
        public let spent: Decimal?
        public var id: String { category }
        public init(category: String, monthlyLimit: Decimal?, spent: Decimal?) { self.category = category; self.monthlyLimit = monthlyLimit; self.spent = spent }
    }
    public let items: [Item]?
    public let totalBudgeted: Decimal?
    public let availableForCategories: Decimal?
    /// True when the user has no budget yet and the items are DINCR's proposal, not the user's.
    public let isProposal: Bool?
    public let period: String?

    public init(items: [Item]?, totalBudgeted: Decimal?, availableForCategories: Decimal?, period: String?, isProposal: Bool? = nil) {
        self.items = items; self.totalBudgeted = totalBudgeted; self.availableForCategories = availableForCategories; self.period = period
        self.isProposal = isProposal
    }
}

/// `PUT /basic/budget`: replaces every limit.
public struct BudgetUpdate: Encodable, Sendable, Equatable {
    public struct Limit: Encodable, Sendable, Equatable {
        public let category: String
        public let monthlyLimit: Decimal
        public init(category: String, monthlyLimit: Decimal) { self.category = category; self.monthlyLimit = monthlyLimit }
    }
    public let items: [Limit]
    public init(items: [Limit]) { self.items = items }
}

/// `GET /user-product/basic/recurring` (Basic).
public struct RecurringList: Decodable, Sendable, Equatable {
    public struct Item: Decodable, Sendable, Equatable, Identifiable {
        public let id: Int
        public let name: String?
        public let amount: Decimal?
        public let category: String?
        public let itemType: String?
        public let frequency: String?
        public let dueDay: Int?
        public let isActive: Bool?
        public init(id: Int, name: String?, amount: Decimal?, category: String?, itemType: String?, frequency: String?, dueDay: Int?, isActive: Bool?) {
            self.id = id; self.name = name; self.amount = amount; self.category = category; self.itemType = itemType
            self.frequency = frequency; self.dueDay = dueDay; self.isActive = isActive
        }
    }
    public let items: [Item]?
    public let monthlyExpenses: Decimal?
    public let annualExpenses: Decimal?
    public init(items: [Item]?, monthlyExpenses: Decimal?, annualExpenses: Decimal?) {
        self.items = items; self.monthlyExpenses = monthlyExpenses; self.annualExpenses = annualExpenses
    }
}

/// Body of `POST /basic/recurring` and `PUT /basic/recurring/{id}`: only the editable fields.
public struct RecurringRequest: Encodable, Sendable, Equatable {
    public static let frequencies = ["weekly", "biweekly", "monthly", "quarterly", "annual"]
    public let name: String
    public let amount: Decimal
    public let category: String
    public let itemType: String
    public let frequency: String
    public let dueDay: Int?
    public let isActive: Bool

    public init(name: String, amount: Decimal, category: String, itemType: String, frequency: String, dueDay: Int?, isActive: Bool) {
        self.name = name; self.amount = amount; self.category = category; self.itemType = itemType
        self.frequency = frequency; self.dueDay = dueDay; self.isActive = isActive
    }
}

/// `GET /user-product/financial-situation`.
public struct FinancialSituation: Decodable, Sendable, Equatable {
    public struct Observed: Decodable, Sendable, Equatable {
        public let windowDays: Int?
        public let incomeCount: Int?
        public let monthlyIncomeAverage: Decimal?
        public let expenseCount: Int?
    }
    public struct DebtSummary: Decodable, Sendable, Equatable {
        public let count: Int?
        public let balance: Decimal?
    }
    public struct GoalSummary: Decodable, Sendable, Equatable {
        public let count: Int?
        public let current: Decimal?
    }
    public let financialProfile: FinancialProfile?
    public let observed: Observed?
    public let debts: DebtSummary?
    public let goals: GoalSummary?
}

/// "Días que trabajás por semana": the backend (and the historical web form) needs it for every
/// income type (`work_days_per_week` is NOT NULL), so the form always shows and sends it.
public enum WorkDays {
    /// The web form's default when there is no profile yet: visible and editable, never hidden.
    public static let defaultValue = 5
    public static let range = 1...7

    /// A whole number of days from 1 to 7, or nil.
    public static func parse(_ text: String) -> Int? {
        guard let days = Int(text.trimmingCharacters(in: .whitespacesAndNewlines)), range.contains(days) else { return nil }
        return days
    }
}

/// The declared financial profile. `PUT /financial-situation` stores exactly this: a field the user
/// left empty is null (unknown), never zero, and an observed average is never copied into it.
public struct FinancialProfile: Codable, Sendable, Equatable {
    public var incomeType: String?
    public var fixedMonthlySalary: Decimal?
    public var hourlyRate: Decimal?
    public var workDaysPerWeek: Int?
    public var hoursPerDay: Decimal?
    public var payFrequency: String?
    public var paydayNote: String?
    public var essentialMonthlyExpenses: Decimal?
    public var liquidSavings: Decimal?
    public var emergencyFundTarget: Decimal?
    public var strategyPreference: String?
    public var discretionaryMonthlyMinimum: Decimal?

    public init() {}

    enum CodingKeys: String, CodingKey {
        case incomeType, fixedMonthlySalary, hourlyRate, workDaysPerWeek, hoursPerDay, payFrequency, paydayNote
        case essentialMonthlyExpenses, liquidSavings, emergencyFundTarget, strategyPreference, discretionaryMonthlyMinimum
    }

    /// Every key is sent, with null for unknown: the backend stores exactly what the user declared.
    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(incomeType, forKey: .incomeType)
        try c.encode(fixedMonthlySalary, forKey: .fixedMonthlySalary)
        try c.encode(hourlyRate, forKey: .hourlyRate)
        try c.encode(workDaysPerWeek, forKey: .workDaysPerWeek)
        try c.encode(hoursPerDay, forKey: .hoursPerDay)
        try c.encode(payFrequency, forKey: .payFrequency)
        try c.encode(paydayNote, forKey: .paydayNote)
        try c.encode(essentialMonthlyExpenses, forKey: .essentialMonthlyExpenses)
        try c.encode(liquidSavings, forKey: .liquidSavings)
        try c.encode(emergencyFundTarget, forKey: .emergencyFundTarget)
        try c.encode(strategyPreference, forKey: .strategyPreference)
        try c.encode(discretionaryMonthlyMinimum, forKey: .discretionaryMonthlyMinimum)
    }
}
