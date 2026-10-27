import Foundation

// JARVIS → Control de dinero (Owner): the money other people owe the Owner ("cuentas por cobrar"),
// by card cycle (it closes on day 21). Read from `GET /finance/receivables`, which never writes;
// a payment or a new charge is an explicit Owner command. Every amount is the backend's: an amount
// it did not send is unknown (nil), never 0, and a negative amount due is the person's credit.
// Android twin: `Receivables.kt`.

/// `GET /finance/receivables`.
public struct ReceivablesReport: Decodable, Sendable, Equatable {
    public struct Cycle: Decodable, Sendable, Equatable {
        public let start: String?
        public let end: String?
    }

    public struct Summary: Decodable, Sendable, Equatable {
        public let totalPending: Decimal?
        public let countOpen: Int?
        public let peopleCount: Int?

        enum CodingKeys: String, CodingKey { case totalPending, countOpen, peopleCount }
        public init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            totalPending = c.lenient(Decimal.self, .totalPending)
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

/// One person who owes the Owner money, for the current card cycle.
public struct Receivable: Decodable, Sendable, Equatable, Identifiable {
    public enum Status: String, Sendable, Equatable {
        case pending, partial, completed, credit, unknown
    }

    public let id: Int
    public let personName: String?
    /// What the person owes now (carried from earlier cycles + this cycle's charges − payments).
    /// Negative: the person has credit.
    public let currentAmountDue: Decimal?
    public let carriedPending: Decimal?
    public let cycleCharges: Decimal?
    public let cyclePayments: Decimal?
    public let status: Status
    /// Charges that came from an additional card (`additional_card_auto`).
    public let isAuto: Bool
    public let history: [ReceivableEntry]

    enum CodingKeys: String, CodingKey {
        case id, personName, currentAmountDue, carriedPending, cycleCharges, cyclePayments, status, isAuto, history
    }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = c.lenient(Int.self, .id) ?? 0
        personName = c.lenient(String.self, .personName)
        currentAmountDue = c.lenient(Decimal.self, .currentAmountDue)
        carriedPending = c.lenient(Decimal.self, .carriedPending)
        cycleCharges = c.lenient(Decimal.self, .cycleCharges)
        cyclePayments = c.lenient(Decimal.self, .cyclePayments)
        status = c.lenient(String.self, .status).flatMap(Status.init(rawValue:)) ?? .unknown
        isAuto = c.lenient(Bool.self, .isAuto) ?? false
        history = c.lenient([ReceivableEntry].self, .history) ?? []
    }

    /// Whether a payment can be recorded: only while the person owes something.
    public var canRecordPayment: Bool { (currentAmountDue ?? 0) > 0 }
}

/// A charge (they owe more) or a payment (they paid), as the backend recorded it. Amounts are positive.
public struct ReceivableEntry: Decodable, Sendable, Equatable, Identifiable {
    public let id: Int
    public let entryType: String?
    public let amount: Decimal?
    public let description: String?
    public let entryDate: String?
    public let sourceType: String?

    enum CodingKeys: String, CodingKey { case id, entryType, amount, description, entryDate, sourceType }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = c.lenient(Int.self, .id) ?? 0
        entryType = c.lenient(String.self, .entryType)
        amount = c.lenient(Decimal.self, .amount)
        description = c.lenient(String.self, .description)
        entryDate = c.lenient(String.self, .entryDate)
        sourceType = c.lenient(String.self, .sourceType)
    }

    public var isPayment: Bool { entryType == "payment" }
}

/// `POST /finance/receivables/{id}/payments`: a payment the person made (cash by default).
public struct ReceivablePaymentRequest: Encodable, Sendable, Equatable {
    public let amount: Decimal
    public let notes: String
    public let paymentDate: String?
    public init(amount: Decimal, notes: String = "", paymentDate: String? = nil) {
        self.amount = amount; self.notes = notes; self.paymentDate = paymentDate
    }
    enum CodingKeys: String, CodingKey { case amount, notes, paymentDate = "payment_date" }
}

/// `POST /finance/receivables/entries`: money someone now owes the Owner.
public struct ReceivableEntryRequest: Encodable, Sendable, Equatable {
    /// The kinds the backend knows (receivable_semantics.py); anything else is stored as "other".
    public static let kinds = ["purchase", "loan", "transfer", "cash", "other"]

    public let personName: String
    public let amount: Decimal
    public let description: String
    public let entryKind: String
    public init(personName: String, amount: Decimal, description: String = "", entryKind: String = "purchase") {
        self.personName = personName; self.amount = amount; self.description = description; self.entryKind = entryKind
    }
    enum CodingKeys: String, CodingKey { case amount, description, personName = "person_name", entryKind = "entry_kind" }
}

/// The answer of both writes: the backend reports a refused write in the body (`status`), not with an HTTP error.
public struct ReceivableWriteResult: Decodable, Sendable, Equatable {
    public let status: String?
    public let message: String?
    public var succeeded: Bool { status == "OK" }
}
