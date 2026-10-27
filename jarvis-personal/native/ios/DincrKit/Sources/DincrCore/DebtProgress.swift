import Foundation

/// How much of the debts has been paid, from the backend's own amounts: the original amount
/// (`total_amount`) minus what is left (`remaining_amount`). Unknown ≠ 0: a debt without a known
/// original amount has no progress, and the total exists only when every debt's is known.
/// Android: `DebtProgress`.
public enum DebtProgress {
    public struct Amounts: Sendable, Equatable {
        public let paid: Decimal
        public let original: Decimal
        /// What is left, as a fraction of the original amount (0...1).
        public var remainingFraction: Double { original > 0 ? NSDecimalNumber(decimal: (original - paid) / original).doubleValue : 0 }
        public var progress: ProgressValue { ProgressValue(current: paid, target: original) }
    }

    /// One debt's paid and original amounts, or nil when the original amount or the balance is unknown.
    public static func of(_ debt: Debt) -> Amounts? {
        guard let original = debt.totalAmount, original > 0, let remaining = debt.remainingAmount else { return nil }
        return Amounts(paid: max(original - remaining, 0), original: original)
    }

    /// All the debts together, or nil when any debt's amounts are unknown (never a partial sum shown as the total).
    public static func total(_ debts: [Debt]) -> Amounts? {
        guard !debts.isEmpty else { return nil }
        var paid: Decimal = 0, original: Decimal = 0
        for debt in debts {
            guard let amounts = of(debt) else { return nil }
            paid += amounts.paid; original += amounts.original
        }
        return Amounts(paid: paid, original: original)
    }

    /// The debt-free date of the plan's strategy (Owner and VIP dashboards), as the backend sends it.
    public struct StrategyDate: Sendable, Equatable {
        /// `YYYY-MM-DD`, or nil when the strategy cannot estimate it.
        public let date: String?
        /// Months earlier than paying only the installments (the Owner's extras); 0 or nil: none.
        public let monthsSaved: Int?
        /// The strategy is waiting for a debt's interest rate (VIP): no date until it is given.
        public let needsRates: Bool
    }

    /// Only a dashboard strategy has a debt-free date; Basic and Free have none (nil).
    public static func strategyDate(_ strategy: PlanStrategy?) -> StrategyDate? {
        guard case .dashboard(let dashboard) = strategy, let plan = dashboard.strategy else { return nil }
        return StrategyDate(date: plan.estimatedDebtFreeDate, monthsSaved: plan.monthsSavedByCurrentExtras, needsRates: plan.needsDebtRates)
    }
}
