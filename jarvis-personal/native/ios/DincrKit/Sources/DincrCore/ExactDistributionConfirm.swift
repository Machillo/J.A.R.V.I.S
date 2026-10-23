import Foundation

/// CONFIRMAR of the Owner's exact-amount distribution (backend/ai/owner_distribution.py).
///
/// The calculated distribution is a plan: it writes nothing. Its answer carries a `ConfirmationPlan`
/// that says what CONFIRMAR would record for each destination. Confirming is the Owner declaring he
/// carried it out: the backend recomputes it, applies it only when it is the split the Owner saw
/// (`ExactDistributionConfirmRequest.expectedItems`) and records it once per confirmation key.
/// Android: `ExactDistributionConfirm.kt`.
public struct ConfirmationPlan: Decodable, Sendable, Equatable {
    public struct DebtTarget: Decodable, Sendable, Equatable {
        public let debtId: Int?
        public let name: String?
        public let amount: Decimal?

        enum CodingKeys: String, CodingKey { case debtId, name, amount }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            debtId = c.lenient(Int.self, .debtId)
            name = c.lenient(String.self, .name)
            amount = c.lenient(Decimal.self, .amount)
        }
    }

    public struct Step: Decodable, Sendable, Equatable {
        public let key: String?
        public let amount: Decimal?
        /// debt_extra_payment, salvavidas_deposit, goal_contribution, investment_reserve, not_recorded.
        public let action: String?
        public let targets: [DebtTarget]
        public let goalName: String?

        enum CodingKeys: String, CodingKey { case key, amount, action, targets, goalName }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            key = c.lenient(String.self, .key)
            amount = c.lenient(Decimal.self, .amount)
            action = c.lenient(String.self, .action)
            targets = c.lenient([DebtTarget].self, .targets) ?? []
            goalName = c.lenient(String.self, .goalName)
        }
    }

    public let steps: [Step]
    public let confirmable: Bool
    public let blockingReasons: [String]
    /// The plan as one value (which debt and goal get what); sent back with CONFIRMAR.
    public let fingerprint: String?

    enum CodingKeys: String, CodingKey { case steps, confirmable, blockingReasons, fingerprint }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        steps = c.lenient([Step].self, .steps) ?? []
        confirmable = c.lenient(Bool.self, .confirmable) ?? false
        blockingReasons = c.lenient([String].self, .blockingReasons) ?? []
        fingerprint = c.lenient(String.self, .fingerprint)
    }
}

public struct ExpectedDistributionItem: Encodable, Sendable, Equatable {
    public let key: String
    public let amount: Decimal
    public init(key: String, amount: Decimal) { self.key = key; self.amount = amount }
}

public struct ExactDistributionConfirmRequest: Encodable, Sendable, Equatable {
    public let amount: Decimal
    public let currency: String
    public let confirmationKey: String
    public let expectedItems: [ExpectedDistributionItem]
    public let planFingerprint: String
}

public struct ExactDistributionConfirmation: Decodable, Sendable, Equatable {
    /// `applied`, or `already_applied` when this confirmation key had already been recorded.
    public let status: String?

    enum CodingKeys: String, CodingKey { case status }
    public init(from decoder: Decoder) throws {
        status = try decoder.container(keyedBy: CodingKeys.self).lenient(String.self, .status)
    }
    public init(status: String?) { self.status = status }
}
