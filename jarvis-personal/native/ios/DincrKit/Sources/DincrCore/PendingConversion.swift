import Foundation

/// `GET /user-product/finance/expenses/pending-conversion`: the expenses typed in dollars that wait
/// for the close (the card's statement cut, or the calendar month without a card) to be converted
/// with one rate, and their totals per currency. They have no colones amount yet: the colones lists
/// and totals leave them out, and the app shows them apart, never as ₡0. `available` is false while
/// the server can't keep an expense pending yet: the editor then always asks for the rate
/// (Android: `PendingConversion`).
public struct PendingConversion: Decodable, Sendable, Equatable {
    public let available: Bool
    public let items: [Item]
    public let totals: [Total]

    public init(available: Bool, items: [Item], totals: [Total]) {
        self.available = available; self.items = items; self.totals = totals
    }

    public struct Item: Decodable, Sendable, Equatable, Identifiable {
        public let movementId: String
        public let id: Int
        public let entryDate: String
        public let description: String
        public let category: String?
        public let originalAmount: Decimal
        public let originalCurrency: String
        public let financialAccountId: Int?

        public init(movementId: String, id: Int, entryDate: String, description: String, category: String?,
                    originalAmount: Decimal, originalCurrency: String, financialAccountId: Int?) {
            self.movementId = movementId; self.id = id; self.entryDate = entryDate; self.description = description
            self.category = category; self.originalAmount = originalAmount; self.originalCurrency = originalCurrency
            self.financialAccountId = financialAccountId
        }

        /// The expense as the editor opens it: in its own currency, still waiting for the close.
        public var movement: Movement {
            Movement(movementId: movementId, sourceId: id, origin: "expense", transactionDate: entryDate, description: description,
                     amount: originalAmount, transactionType: .expense, category: category, originalAmount: originalAmount,
                     originalCurrency: originalCurrency, financialAccountId: financialAccountId)
        }
    }

    public struct Total: Decodable, Sendable, Equatable, Identifiable {
        public let currency: String
        public let amount: Decimal
        public let count: Int
        public var id: String { currency }

        public init(currency: String, amount: Decimal, count: Int) { self.currency = currency; self.amount = amount; self.count = count }
    }

    public static let unavailable = PendingConversion(available: false, items: [], totals: [])
}
