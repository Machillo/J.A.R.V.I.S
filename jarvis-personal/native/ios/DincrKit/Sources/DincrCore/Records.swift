import Foundation

// JARVIS → Registros (Owner): the money timeline (`GET /finance/timeline`: the known incomes and
// obligations ahead and the balance they leave) and the account reconciliation
// (`GET /finance/reconciliation`: each tracked account's expected and real balance). Both reads
// never write; confirming a real balance is an explicit Owner command. Every amount is the
// backend's: one it did not send is unknown (nil), never 0. Android twin: `Records.kt`.

/// `GET /finance/timeline`.
public struct MoneyTimeline: Decodable, Sendable, Equatable {
    public struct Event: Decodable, Sendable, Equatable, Identifiable {
        public let date: String?
        public let name: String?
        /// `income`, `recurring_expense`, `debt_payment` or `goal` (a reminder that moves nothing).
        public let kind: String?
        public let amount: Decimal?
        /// The change to the available balance (negative for an outflow; 0 for a reminder).
        public let impact: Decimal?
        public let projectedBalance: Decimal?
        public let note: String?
        public var id: String { "\(date ?? "")|\(name ?? "")|\(kind ?? "")" }

        enum CodingKeys: String, CodingKey { case date, name, kind, amount, impact, projectedBalance, note }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            date = c.lenient(String.self, .date); name = c.lenient(String.self, .name); kind = c.lenient(String.self, .kind)
            amount = c.lenient(Decimal.self, .amount); impact = c.lenient(Decimal.self, .impact)
            projectedBalance = c.lenient(Decimal.self, .projectedBalance); note = c.lenient(String.self, .note)
        }
    }

    public let startDate: String?
    public let endDate: String?
    public let openingAvailable: Decimal?
    public let endingAvailable: Decimal?
    public let events: [Event]
    public let assumptions: [String]

    enum CodingKeys: String, CodingKey { case startDate, endDate, openingAvailable, endingAvailable, events, assumptions }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        startDate = c.lenient(String.self, .startDate); endDate = c.lenient(String.self, .endDate)
        openingAvailable = c.lenient(Decimal.self, .openingAvailable); endingAvailable = c.lenient(Decimal.self, .endingAvailable)
        events = c.lenient([Event].self, .events) ?? []
        assumptions = c.lenient([String].self, .assumptions) ?? []
    }

    /// The events grouped by day, in the backend's order.
    public var days: [(date: String, events: [Event])] {
        var order: [String] = []
        var grouped: [String: [Event]] = [:]
        for event in events {
            let key = event.date ?? ""
            if grouped[key] == nil { order.append(key) }
            grouped[key, default: []].append(event)
        }
        return order.map { ($0, grouped[$0] ?? []) }
    }
}

/// `GET /finance/reconciliation`.
public struct Reconciliation: Decodable, Sendable, Equatable {
    public struct Account: Decodable, Sendable, Equatable, Identifiable {
        public let accountId: Int
        public let accountName: String?
        public let institution: String?
        public let last4: String?
        public let currency: String?
        /// The last declared balance plus the movements recorded since.
        public let expectedBalance: Decimal?
        /// The last declared (real) balance.
        public let realBalance: Decimal?
        public let difference: Decimal?
        public let movementsSinceBalance: Int?
        public let balanceAsOf: String?
        public let needsReview: Bool
        public var id: Int { accountId }

        enum CodingKeys: String, CodingKey {
            case accountId, accountName, institution, last4, currency, expectedBalance, realBalance, difference, movementsSinceBalance, balanceAsOf, status
        }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            accountId = c.lenient(Int.self, .accountId) ?? 0
            accountName = c.lenient(String.self, .accountName); institution = c.lenient(String.self, .institution)
            last4 = c.lenient(String.self, .last4); currency = c.lenient(String.self, .currency)
            expectedBalance = c.lenient(Decimal.self, .expectedBalance); realBalance = c.lenient(Decimal.self, .realBalance)
            difference = c.lenient(Decimal.self, .difference); movementsSinceBalance = c.lenient(Int.self, .movementsSinceBalance)
            balanceAsOf = c.lenient(String.self, .balanceAsOf)
            needsReview = c.lenient(String.self, .status) == "needs_review"
        }
    }

    public struct Summary: Decodable, Sendable, Equatable {
        public let accounts: Int?
        public let needsReview: Int?
        public let unlinked: Int?
        public let possibleDuplicates: Int?
        public let untrackedAccounts: Int?

        enum CodingKeys: String, CodingKey { case accounts, needsReview, unlinked, possibleDuplicates, untrackedAccounts }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            accounts = c.lenient(Int.self, .accounts); needsReview = c.lenient(Int.self, .needsReview)
            unlinked = c.lenient(Int.self, .unlinked); possibleDuplicates = c.lenient(Int.self, .possibleDuplicates)
            untrackedAccounts = c.lenient(Int.self, .untrackedAccounts)
        }
    }

    public let accounts: [Account]
    public let summary: Summary?
    public let note: String?

    enum CodingKeys: String, CodingKey { case accounts, summary, note }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        accounts = c.lenient([Account].self, .accounts) ?? []
        summary = c.lenient(Summary.self, .summary)
        note = c.lenient(String.self, .note)
    }
}

/// `POST /finance/reconciliation/{account_id}/confirm`: the account's real balance today, as the Owner checked it.
public struct ReconciliationConfirmRequest: Encodable, Sendable, Equatable {
    public let realBalance: Decimal
    public let note: String
    public init(realBalance: Decimal, note: String = "") { self.realBalance = realBalance; self.note = note }
    enum CodingKeys: String, CodingKey { case note, realBalance = "real_balance" }
}

public struct ReconciliationConfirmResult: Decodable, Sendable, Equatable {
    public let status: String?
    public let confirmed: Bool?
}
