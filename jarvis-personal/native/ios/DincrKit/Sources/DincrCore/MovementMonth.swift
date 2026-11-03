import Foundation

/// Movimientos shows one month at a time (the current one when it opens), not the whole history.
/// The backend still returns every movement; this narrows what is on screen. A search looks
/// through every month, so an old movement can still be found by name. Android: `MovementMonth.kt`.
public enum MovementMonth {
    /// The rows to list: with a search, every month that matches; without one, only `month` ("YYYY-MM").
    public static func rows(_ rows: [Movement], month: String, query: String) -> [Movement] {
        let searching = !query.trimmingCharacters(in: .whitespaces).isEmpty
        return rows.filter { searching || ($0.day ?? "").hasPrefix(month) }
    }
}

/// What the rows on screen add up to, in the base currency: the running totals of Movimientos.
/// Only what is registered in the list: a dollar expense waiting for its close has no colones amount
/// and is not a row here, and no row of a kind is unknown, never ₡0. Android: `MovementTotals`.
public struct MovementTotals: Sendable, Equatable {
    public let income: Decimal?
    public let expenses: Decimal?
    /// The Owner's debt payments, a line of their own in his ledger; nil when there are none.
    public let debtPaid: Decimal?

    /// Income minus expenses and debt payments; nil while either side is unknown.
    public var result: Decimal? {
        guard let income, let expenses else { return nil }
        return income - expenses - (debtPaid ?? 0)
    }

    public init(_ rows: [Movement]) {
        var income: Decimal?, expenses: Decimal?, debtPaid: Decimal?
        for row in rows {
            // The Owner's rows say what they count as: a transfer or a loan is neither income nor spending.
            switch row.countsIn ?? row.transactionType.rawValue {
            case "income": income = (income ?? 0) + row.amount
            case "expense", "expenses": expenses = (expenses ?? 0) + row.amount
            case "refunds": expenses = (expenses ?? 0) - row.amount
            case "debt_payments": debtPaid = (debtPaid ?? 0) + row.amount
            default: break
            }
        }
        self.income = income; self.expenses = expenses.map { max($0, 0) }; self.debtPaid = debtPaid
    }
}
