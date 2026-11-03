import Foundation

/// Whether a new movement gets a review before saving: only where a slip costs more, so everyday
/// expenses save directly. Presentation only: it never changes what is saved. Android: `MovementReview.kt`.
public enum MovementReview {
    /// From here an amount is unusual enough to read twice. Other currencies never reach the entry today.
    static let largeAmount: [String: Decimal] = ["CRC": 500_000, "USD": 1_000]

    /// `convertsNow`: typed in another currency and converted with a rate the user typed.
    public static func isNeeded(amount: Decimal, currency: String, convertsNow: Bool) -> Bool {
        if convertsNow { return true }
        guard let large = largeAmount[currency.uppercased()] else { return false }
        return amount >= large
    }
}
