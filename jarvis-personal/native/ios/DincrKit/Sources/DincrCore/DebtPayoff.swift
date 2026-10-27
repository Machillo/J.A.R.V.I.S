import Foundation

/// When the debts are expected to be paid off, from the backend's per-debt estimate
/// (`Debt.estimatedPayoffDate`, debt_payoff.py). Nothing is calculated here: the debt-free month is
/// the latest of the backend's dates, and only when every unpaid debt has one (UNKNOWN ≠ a date).
/// Android: `DebtPayoff`.
public enum DebtPayoff {
    public struct Summary: Sendable, Equatable {
        /// `YYYY-MM-DD` of the last installment of all, or nil when some unpaid debt has no estimate.
        public let debtFreeDate: String?
        /// Unpaid debts the backend could not estimate (unknown rate, no payment, or a payment that
        /// does not cover the interest).
        public let unestimated: Int
        /// Unpaid debts.
        public let active: Int
    }

    public static func summary(_ debts: [Debt]) -> Summary {
        let active = debts.filter { ($0.remainingAmount ?? 0) > 0 }
        let dates = active.compactMap(\.estimatedPayoffDate)
        let unestimated = active.count - dates.count
        return Summary(debtFreeDate: unestimated == 0 ? dates.max() : nil, unestimated: unestimated, active: active.count)
    }

    /// "oct 2027" / "Oct 2027" for a `YYYY-MM-DD` date.
    public static func monthLabel(_ date: String, language: AppLanguage = .current) -> String {
        OwnerReading.monthLabel(String(date.prefix(7)), language: language)
    }
}
