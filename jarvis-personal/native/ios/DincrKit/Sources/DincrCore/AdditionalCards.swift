import Foundation

// JARVIS → Control de dinero (Owner): the cards billed to the Owner but carried by someone else.
// A purchase notice on one of these cards is that person's debt (the backend settles it into
// their receivable), not the Owner's expense. Read from `GET /finance/additional-cards`, which
// never writes; marking or unmarking a card is an explicit Owner command. Android twin:
// `AdditionalCards` in `Receivables.kt`.

/// One card the Owner marked as carried by a person.
public struct AdditionalCard: Decodable, Sendable, Equatable, Identifiable {
    public let cardLast4: String
    public let personName: String?
    public var id: String { cardLast4 }

    enum CodingKeys: String, CodingKey { case cardLast4, personName }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        cardLast4 = c.lenient(String.self, .cardLast4) ?? ""
        personName = c.lenient(String.self, .personName)
    }
}

/// `GET /finance/additional-cards`.
public struct AdditionalCardsList: Decodable, Sendable, Equatable {
    public let items: [AdditionalCard]

    enum CodingKeys: String, CodingKey { case items }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        items = (c.lenient([AdditionalCard].self, .items) ?? []).filter { !$0.cardLast4.isEmpty }
    }
}

/// `PUT /finance/additional-cards/{last4}`: who carries the card.
public struct AdditionalCardRequest: Encodable, Sendable, Equatable {
    public let personName: String
    public init(personName: String) { self.personName = personName }
    enum CodingKeys: String, CodingKey { case personName = "person_name" }

    /// The last 4 digits the backend accepts: exactly four digits, nothing else.
    public static func last4(_ text: String) -> String? {
        let digits = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return digits.count == 4 && digits.allSatisfy(\.isASCII) && digits.allSatisfy(\.isNumber) ? digits : nil
    }
}

/// The answer of marking (`settled_purchases`) or unmarking (`released_purchases`) a card.
public struct AdditionalCardResult: Decodable, Sendable, Equatable {
    public let status: String?
    public let settledPurchases: Int?
    public let releasedPurchases: Int?
}
