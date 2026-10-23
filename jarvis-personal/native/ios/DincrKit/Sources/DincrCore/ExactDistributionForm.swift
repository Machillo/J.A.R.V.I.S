import Foundation

/// The Owner's exact-amount form (Plan → Distribución de dinero → Monto exacto). A result always
/// belongs to the amount it was calculated from: editing the amount drops it, and an answer that
/// arrives for an amount the Owner has since changed is ignored. Android: `ExactDistributionForm`.
public struct ExactDistributionForm: Equatable, Sendable {
    public private(set) var amountText: String
    public private(set) var result: DashboardStrategy?
    public var error: String?
    /// What CONFIRMAR would record for `result`; nil before a result.
    public private(set) var plan: ConfirmationPlan?
    /// One key per calculated result: repeating a confirmation (retry, double tap) records it once.
    public private(set) var confirmationKey: String?
    /// Set once the backend recorded this result: the Owner declared he carried it out.
    public private(set) var confirmation: ExactDistributionConfirmation?

    public init(amountText: String = "") {
        self.amountText = amountText
        self.result = nil
        self.error = nil
        self.plan = nil
        self.confirmationKey = nil
        self.confirmation = nil
    }

    /// A new amount: the previous result (and error) no longer describe it.
    public mutating func edit(_ text: String) {
        self = ExactDistributionForm(amountText: text)
    }

    /// The answer for `text`; kept only when it is still the amount on screen. A new result gets a new key.
    public mutating func calculated(for text: String, _ strategy: DashboardStrategy?, plan: ConfirmationPlan? = nil,
                                    key: String = UUID().uuidString) {
        guard text == amountText else { return }
        result = strategy
        error = nil
        self.plan = plan
        confirmationKey = key
        confirmation = nil
    }

    /// CONFIRMAR is offered only for a calculated result the backend says it can record, once.
    public var canConfirm: Bool { result != nil && plan?.confirmable == true && confirmationKey != nil && confirmation == nil }

    /// The split the Owner reviewed, sent with CONFIRMAR: the backend records nothing when its own differs.
    public func confirmRequest(amount: Decimal) -> ExactDistributionConfirmRequest? {
        guard let result, let confirmationKey, let fingerprint = plan?.fingerprint else { return nil }
        let items = (result.allocationItems ?? []).compactMap { item -> ExpectedDistributionItem? in
            guard let key = item.key, let value = item.amount else { return nil }
            // JSONDecoder reads a Decimal through Double (114614.1 → 114614.09999…): back to whole cents.
            return ExpectedDistributionItem(key: key, amount: Self.cents(value))
        }
        return ExactDistributionConfirmRequest(amount: Self.cents(amount), currency: "CRC", confirmationKey: confirmationKey,
                                               expectedItems: items, planFingerprint: fingerprint)
    }

    /// `value` rounded to whole cents (half up), as the backend reads money.
    static func cents(_ value: Decimal) -> Decimal {
        var input = value
        var rounded = Decimal()
        NSDecimalRound(&rounded, &input, 2, .plain)
        return rounded
    }

    /// The backend's answer for `key`; kept only when it is still this result's key.
    public mutating func confirmed(key: String, _ answer: ExactDistributionConfirmation) {
        guard key == confirmationKey else { return }
        confirmation = answer
        error = nil
    }
}
