import Foundation

/// How the Owner orders his debts (OW-3): as saved, by balance or by annual rate, either way.
/// An unknown balance or rate is never read as 0: those debts go last in both directions.
/// Android: `com.dincr.data.DebtOrder`.
public enum DebtOrder: String, CaseIterable, Sendable {
    case saved, balanceHigh, balanceLow, rateHigh, rateLow

    public func sorted(_ debts: [Debt]) -> [Debt] {
        switch self {
        case .saved: return debts
        case .balanceHigh: return Self.order(debts, by: { $0.remainingAmount }, descending: true)
        case .balanceLow: return Self.order(debts, by: { $0.remainingAmount }, descending: false)
        case .rateHigh: return Self.order(debts, by: { $0.rateForEditing }, descending: true)
        case .rateLow: return Self.order(debts, by: { $0.rateForEditing }, descending: false)
        }
    }

    /// Stable: equal values keep the saved order; unknown values keep it too, after the known ones.
    private static func order(_ debts: [Debt], by value: (Debt) -> Decimal?, descending: Bool) -> [Debt] {
        let indexed = debts.enumerated().map { (offset: $0.offset, debt: $0.element, value: value($0.element)) }
        let known = indexed.filter { $0.value != nil }.sorted {
            if $0.value! == $1.value! { return $0.offset < $1.offset }
            return descending ? $0.value! > $1.value! : $0.value! < $1.value!
        }
        let unknown = indexed.filter { $0.value == nil }
        return (known + unknown).map(\.debt)
    }
}
