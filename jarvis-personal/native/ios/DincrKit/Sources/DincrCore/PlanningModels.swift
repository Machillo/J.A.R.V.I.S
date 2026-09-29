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

    public init(id: Int, name: String?, debtType: String? = "other", totalAmount: Decimal? = nil, remainingAmount: Decimal?,
                monthlyPayment: Decimal? = nil, interestRate: Decimal? = nil, paymentDay: Int? = nil,
                nextPaymentDate: String? = nil, progressPercent: Double? = nil) {
        self.id = id; self.name = name; self.debtType = debtType; self.totalAmount = totalAmount
        self.remainingAmount = remainingAmount; self.monthlyPayment = monthlyPayment; self.interestRate = interestRate
        self.paymentDay = paymentDay; self.nextPaymentDate = nextPaymentDate; self.progressPercent = progressPercent
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
    public static func checkAmount(_ amount: Decimal) throws {
        var value = amount
        var rounded = Decimal()
        NSDecimalRound(&rounded, &value, AmountInput.maxFractionDigits, .plain)
        guard amount > 0, amount <= AmountInput.maxAmount, rounded == amount else {
            throw APIError(kind: .validation, message: AppLanguage.current.pick(
                "El monto no es válido.", "The amount is not valid."))
        }
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
