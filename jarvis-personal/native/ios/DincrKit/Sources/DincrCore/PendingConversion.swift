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
    /// The closes the waiting expenses belong to (3d), oldest first: each converts with one rate.
    public let periods: [Period]
    /// The server converts them by itself at the close, with the dollar of that day. False from a
    /// server that can't yet: the app then promises nothing, and asks for the rate.
    public let autoClose: Bool

    public init(available: Bool, items: [Item], totals: [Total], periods: [Period] = [], autoClose: Bool = false) {
        self.available = available; self.items = items; self.totals = totals; self.periods = periods; self.autoClose = autoClose
    }

    enum CodingKeys: String, CodingKey { case available, items, totals, periods, autoClose }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        available = try c.decode(Bool.self, forKey: .available)
        items = try c.decode([Item].self, forKey: .items)
        totals = try c.decode([Total].self, forKey: .totals)
        // A server without the close (3c only) sends no periods: nothing can be closed yet.
        periods = try c.decodeIfPresent([Period].self, forKey: .periods) ?? []
        autoClose = try c.decodeIfPresent(Bool.self, forKey: .autoClose) ?? false
    }

    /// One close: a card's statement cycle, or a calendar month without a card. It converts once it
    /// has ended (`closable`). A card without a declared cut day falls in its month (`cutDayMissing`).
    public struct Period: Decodable, Sendable, Equatable, Identifiable {
        public let key: String
        public let kind: String
        public let start: String
        public let end: String
        public let closable: Bool
        public let cutDayMissing: Bool
        public let accountId: Int?
        public let accountName: String?
        public let accountLast4: String?
        public let totals: [Total]
        public let count: Int
        public var id: String { key }
        public var isCard: Bool { kind == "card" }

        public init(key: String, kind: String, start: String, end: String, closable: Bool, cutDayMissing: Bool = false,
                    accountId: Int? = nil, accountName: String? = nil, accountLast4: String? = nil, totals: [Total], count: Int) {
            self.key = key; self.kind = kind; self.start = start; self.end = end; self.closable = closable
            self.cutDayMissing = cutDayMissing; self.accountId = accountId; self.accountName = accountName
            self.accountLast4 = accountLast4; self.totals = totals; self.count = count
        }
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
        /// The close it belongs to (`Period.key`); nil from a server without the close.
        public let periodKey: String?
        /// In the base currency at the purchase day's rate, only to follow what is owed; nil: unknown.
        /// The final amount comes at the close, with that day's rate.
        public let estimatedAmount: Decimal?

        public init(movementId: String, id: Int, entryDate: String, description: String, category: String?,
                    originalAmount: Decimal, originalCurrency: String, financialAccountId: Int?, periodKey: String? = nil,
                    estimatedAmount: Decimal? = nil) {
            self.movementId = movementId; self.id = id; self.entryDate = entryDate; self.description = description
            self.category = category; self.originalAmount = originalAmount; self.originalCurrency = originalCurrency
            self.financialAccountId = financialAccountId; self.periodKey = periodKey; self.estimatedAmount = estimatedAmount
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
        /// Left out by the server when one of its expenses has no estimate: never a partial sum.
        public let estimatedAmount: Decimal?
        public var id: String { currency }

        public init(currency: String, amount: Decimal, count: Int, estimatedAmount: Decimal? = nil) {
            self.currency = currency; self.amount = amount; self.count = count; self.estimatedAmount = estimatedAmount
        }
    }

    public static let unavailable = PendingConversion(available: false, items: [], totals: [])

    /// What the waiting dollars on screen add to the expenses: with a search every month, without
    /// one only `month` (`YYYY-MM`), like the colones rows. `sum` nil: none has an estimate.
    public func estimate(month: String, query: String) -> PendingEstimate {
        let searching = !query.trimmingCharacters(in: .whitespaces).isEmpty
        let shown = items.filter { (searching || $0.entryDate.hasPrefix(month)) && SearchText.matches(query, in: [$0.description, $0.category]) }
        let known = shown.compactMap(\.estimatedAmount)
        return PendingEstimate(sum: known.isEmpty ? nil : known.reduce(0, +), withoutEstimate: shown.count - known.count)
    }
}

public struct PendingEstimate: Sendable, Equatable {
    public let sum: Decimal?
    /// Waiting expenses on screen that couldn't be estimated: they are named, not counted as 0.
    public let withoutEstimate: Int

    public init(sum: Decimal?, withoutEstimate: Int) { self.sum = sum; self.withoutEstimate = withoutEstimate }
}

/// Body of `POST /user-product/finance/expenses/pending-conversion/close`: one rate for one close.
public struct PendingClose: Encodable, Sendable, Equatable {
    public let periodKey: String
    public let exchangeRate: Decimal

    public init(periodKey: String, exchangeRate: Decimal) { self.periodKey = periodKey; self.exchangeRate = exchangeRate }
}

/// What a close converted: how many expenses and their total in the base currency.
public struct PendingCloseResult: Decodable, Sendable, Equatable {
    public let converted: Int
    public let amount: Decimal
    public let currency: String
    public let exchangeRate: Decimal
}
