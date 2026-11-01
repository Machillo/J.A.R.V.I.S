import Foundation

/// `POST /finance/strategy-vip/debt-scenario` (VIP): a what-if on one debt that is not saved — pay it
/// off, an extra payment to it, a new debt, refinance it (DS-2) or consolidate several (DS-2). Every answer is the money left each month after
/// essentials and debt payments; nil is unknown, never ₡0 (Android: `DebtScenarioRequest`).
public struct DebtScenarioRequest: Encodable, Sendable, Equatable {
    public enum Kind: String, Encodable, Sendable, CaseIterable {
        case payOff = "pay_off", extraPayment = "extra_payment", newDebt = "new_debt", refinance, consolidate
    }
    public let kind: Kind
    public let debtId: Int?
    public let amount: Decimal?
    public let monthlyPayment: Decimal?
    public let annualRate: Decimal?
    public let termMonths: Int?
    public let name: String?
    public var debtIds: [Int]? = nil

    public static func payOff(debtId: Int) -> DebtScenarioRequest {
        DebtScenarioRequest(kind: .payOff, debtId: debtId, amount: nil, monthlyPayment: nil, annualRate: nil, termMonths: nil, name: nil)
    }

    public static func extraPayment(debtId: Int, amount: Decimal) -> DebtScenarioRequest {
        DebtScenarioRequest(kind: .extraPayment, debtId: debtId, amount: amount, monthlyPayment: nil, annualRate: nil, termMonths: nil, name: nil)
    }

    /// The payment, or the rate and term for DINCR to compute it.
    public static func newDebt(name: String?, amount: Decimal, monthlyPayment: Decimal?, annualRate: Decimal?, termMonths: Int?) -> DebtScenarioRequest {
        DebtScenarioRequest(kind: .newDebt, debtId: nil, amount: amount, monthlyPayment: monthlyPayment, annualRate: annualRate, termMonths: termMonths, name: name)
    }

    /// One debt for a new loan at `annualRate` over `termMonths`; `fee` (optional) is borrowed too.
    public static func refinance(debtId: Int, annualRate: Decimal, termMonths: Int, fee: Decimal?) -> DebtScenarioRequest {
        DebtScenarioRequest(kind: .refinance, debtId: debtId, amount: fee, monthlyPayment: nil, annualRate: annualRate, termMonths: termMonths, name: nil)
    }

    /// Several debts paid with one new loan.
    public static func consolidate(debtIds: [Int], annualRate: Decimal, termMonths: Int, fee: Decimal?) -> DebtScenarioRequest {
        DebtScenarioRequest(kind: .consolidate, debtId: nil, amount: fee, monthlyPayment: nil, annualRate: annualRate, termMonths: termMonths, name: nil, debtIds: debtIds)
    }
}

public struct DebtScenarioResult: Decodable, Sendable, Equatable {
    public struct Leftover: Decodable, Sendable, Equatable {
        public let current: Decimal?
        public let scenario: Decimal?
        public let change: Decimal?
    }
    public struct DebtView: Decodable, Sendable, Equatable {
        public let id: Int?
        public let name: String?
        public let remainingAmount: Decimal?
        public let monthlyPayment: Decimal?
        public let interestRate: Decimal?
        /// `declared` (the user gave the payment) or `computed` (from rate and term), new debts only.
        public let monthlyPaymentSource: String?
    }
    /// The lender lowers the installment: same term, more left each month.
    public struct LowerInstallment: Decodable, Sendable, Equatable {
        public let monthlyPayment: Decimal?
        public let monthlyLeftover: Decimal?
        public let change: Decimal?
    }
    /// The lender shortens the term: same installment, fewer months and less interest.
    public struct ShorterTerm: Decodable, Sendable, Equatable {
        public let monthlyPayment: Decimal?
        public let monthlyLeftover: Decimal?
        public let monthsSaved: Int?
        public let interestSaved: Decimal?
    }
    public struct Options: Decodable, Sendable, Equatable {
        public let lowerInstallment: LowerInstallment?
        public let shorterTerm: ShorterTerm?
    }
    public struct Payoff: Decodable, Sendable, Equatable {
        public let months: Int?
        public let interest: Decimal?
    }
    /// Refinance / consolidate: today's debts against the new loan.
    public struct Comparison: Decodable, Sendable, Equatable {
        public struct Side: Decodable, Sendable, Equatable {
            public let monthlyPayment: Decimal?
            public let months: Int?
            public let interest: Decimal?
            public let fee: Decimal?
        }
        public let current: Side?
        public let scenario: Side?
        /// Today's interest minus the new loan's interest and fee: positive saves, negative costs more.
        public let totalSaved: Decimal?
    }

    public let kind: String
    public let debt: DebtView?
    public let monthlyLeftover: Leftover
    public let oneTimeAmount: Decimal?
    public let liquidSavingsAfter: Decimal?
    public let options: Options?
    public let payoff: Payoff?
    public let warnings: [String]?
    public let explanation: String?
    public let debts: [DebtView]?
    public let comparison: Comparison?
}

extension DincrService {
    public func debtScenario(_ request: DebtScenarioRequest) async throws -> DebtScenarioResult {
        try await client.send("POST", "/user-product/finance/strategy-vip/debt-scenario", body: request)
    }
}
