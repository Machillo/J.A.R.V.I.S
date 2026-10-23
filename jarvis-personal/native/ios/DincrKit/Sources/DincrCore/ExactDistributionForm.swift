import Foundation

/// The Owner's exact-amount form (Plan → Distribución de dinero → Monto exacto). A result always
/// belongs to the amount it was calculated from: editing the amount drops it, and an answer that
/// arrives for an amount the Owner has since changed is ignored. Android: `ExactDistributionForm`.
public struct ExactDistributionForm: Equatable, Sendable {
    public private(set) var amountText: String
    public private(set) var result: DashboardStrategy?
    public var error: String?

    public init(amountText: String = "") {
        self.amountText = amountText
        self.result = nil
        self.error = nil
    }

    /// A new amount: the previous result (and error) no longer describe it.
    public mutating func edit(_ text: String) {
        amountText = text
        result = nil
        error = nil
    }

    /// The answer for `text`; kept only when it is still the amount on screen.
    public mutating func calculated(for text: String, _ strategy: DashboardStrategy?) {
        guard text == amountText else { return }
        result = strategy
        error = nil
    }
}
