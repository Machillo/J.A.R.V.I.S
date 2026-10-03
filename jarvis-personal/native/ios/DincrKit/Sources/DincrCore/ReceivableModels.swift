import Foundation

// JARVIS · Control de dinero: the Owner's cuentas por cobrar (the historical web Receivables page).
// `GET /finance/receivables/view` (owner/admin only): the same list and figures as the web's
// `GET /finance/receivables`, read only (no sync, nothing stored). Every figure is the backend's;
// a missing or odd value is unknown (nil, shown as "—"), never zero. Android twin: `Receivables.kt`.

/// `GET /finance/receivables/view`.
public struct ReceivablesReport: Decodable, Sendable, Equatable {
    public struct Cycle: Decodable, Sendable, Equatable {
        public let start: String?
        public let end: String?
    }

    public struct Summary: Decodable, Sendable, Equatable {
        public let totalPending: Decimal?
        public let carriedPending: Decimal?
        public let cycleCharges: Decimal?
        public let cyclePayments: Decimal?
        public let countOpen: Int?
        public let peopleCount: Int?

        enum CodingKeys: String, CodingKey { case totalPending, carriedPending, cycleCharges, cyclePayments, countOpen, peopleCount }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            totalPending = c.lenient(Decimal.self, .totalPending)
            carriedPending = c.lenient(Decimal.self, .carriedPending)
            cycleCharges = c.lenient(Decimal.self, .cycleCharges)
            cyclePayments = c.lenient(Decimal.self, .cyclePayments)
            countOpen = c.lenient(Int.self, .countOpen)
            peopleCount = c.lenient(Int.self, .peopleCount)
        }
    }

    public let cycle: Cycle?
    public let items: [Receivable]
    public let summary: Summary?

    enum CodingKeys: String, CodingKey { case cycle, items, summary }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        cycle = c.lenient(Cycle.self, .cycle)
        items = c.lenient([Receivable].self, .items) ?? []
        summary = c.lenient(Summary.self, .summary)
    }
}

/// One person who owes the Owner money, with the current card cycle's figures.
public struct Receivable: Decodable, Sendable, Equatable, Identifiable {
    public struct Entry: Decodable, Sendable, Equatable, Identifiable {
        public let id: Int
        /// "charge" (lent or charged) or "payment" (received).
        public let entryType: String?
        public let amount: Decimal?
        public let description: String?
        public let entryDate: String?

        public var isPayment: Bool { entryType == "payment" }

        enum CodingKeys: String, CodingKey { case id, entryType, amount, description, entryDate }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            id = try c.decode(Int.self, forKey: .id)
            entryType = c.lenient(String.self, .entryType)
            amount = c.lenient(Decimal.self, .amount)
            description = c.lenient(String.self, .description)
            entryDate = c.lenient(String.self, .entryDate)
        }
    }

    public let id: Int
    public let personName: String?
    /// "pending", "partial", "completed" or "credit" (the person paid more than owed).
    public let status: String?
    public let currentAmountDue: Decimal?
    public let carriedPending: Decimal?
    public let cycleCharges: Decimal?
    public let cyclePayments: Decimal?
    public let notes: String?
    public let isAuto: Bool?
    public let history: [Entry]

    enum CodingKeys: String, CodingKey {
        case id, personName, status, currentAmountDue, carriedPending, cycleCharges, cyclePayments, notes, isAuto, history
    }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(Int.self, forKey: .id)
        personName = c.lenient(String.self, .personName)
        status = c.lenient(String.self, .status)
        currentAmountDue = c.lenient(Decimal.self, .currentAmountDue)
        carriedPending = c.lenient(Decimal.self, .carriedPending)
        cycleCharges = c.lenient(Decimal.self, .cycleCharges)
        cyclePayments = c.lenient(Decimal.self, .cyclePayments)
        notes = c.lenient(String.self, .notes)
        isAuto = c.lenient(Bool.self, .isAuto)
        history = c.lenient([Entry].self, .history) ?? []
    }
}
