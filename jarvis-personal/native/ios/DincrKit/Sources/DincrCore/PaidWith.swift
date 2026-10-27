import Foundation

/// `GET /user-product/finance/expenses/paid-with-options`: the user's own active accounts and cards
/// an expense can say it was paid with (cards first). `available` is false while the server does not
/// store the link yet: the editor then hides "Pagado con" (Android: `PaidWithOptions`).
public struct PaidWithOptions: Decodable, Sendable, Equatable {
    public let available: Bool
    public let items: [Option]

    public init(available: Bool, items: [Option]) { self.available = available; self.items = items }

    public struct Option: Decodable, Sendable, Equatable, Identifiable, Hashable {
        public let id: Int
        public let accountName: String?
        public let bankName: String?
        public let accountType: String?
        public let accountLast4: String?
        public let currency: String?

        public init(id: Int, accountName: String?, bankName: String?, accountType: String?, accountLast4: String?, currency: String?) {
            self.id = id; self.accountName = accountName; self.bankName = bankName
            self.accountType = accountType; self.accountLast4 = accountLast4; self.currency = currency
        }

        public var isCard: Bool { accountType == "credit_card" }

        /// "BAC · Tarjeta de crédito ••5678" — what the user named, never more than the last 4 digits.
        public var label: String {
            let last4 = accountLast4.flatMap { $0.isEmpty ? nil : "••\($0)" }
            return [bankName, [accountName, last4].compactMap { $0 }.joined(separator: " ")]
                .compactMap { $0?.isEmpty == false ? $0 : nil }.joined(separator: " · ")
        }
    }

    /// What the editor offers: nothing while unavailable or without own accounts.
    public var offered: [Option] { available ? items : [] }
}

/// The "paid with" part of an edit: an older screen leaves the link as it is (the key is not sent);
/// the editor that shows the picker sends the choice, `nil` clearing it.
public enum PaidWithChange: Sendable, Equatable {
    case unchanged
    case set(Int?)
}
