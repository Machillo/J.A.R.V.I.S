import Foundation

// Plan → Gastos fijos (Owner): the Owner's fixed expenses (`fixed_expenses`, the same table the
// Salvavidas and the Owner strategy read), listed, added, edited and removed through `/finance/
// fixed-expenses` (INTERNAL_ONLY: the backend refuses everyone else). VIP manages the same idea as
// recurring expenses (`/user-product/basic/recurring`). Removing deactivates the row, as the backend does.
// Android twin: `FixedExpenses.kt`.

/// One row of `GET /finance/fixed-expenses`.
public struct OwnerFixedExpense: Decodable, Sendable, Equatable, Identifiable {
    public let id: Int
    public let name: String?
    public let category: String?
    public let expectedAmount: Decimal?
    public let currency: String?
    public let frequency: String?
    public let intervalMonths: Int?
    public let dueDay: Int?
    public let isActive: Bool?

    enum CodingKeys: String, CodingKey { case id, name, category, expectedAmount, currency, frequency, intervalMonths, dueDay, isActive }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(Int.self, forKey: .id)
        name = c.lenient(String.self, .name)
        category = c.lenient(String.self, .category)
        expectedAmount = c.lenient(Decimal.self, .expectedAmount)
        currency = c.lenient(String.self, .currency)
        frequency = c.lenient(String.self, .frequency)
        intervalMonths = c.lenient(Int.self, .intervalMonths)
        dueDay = c.lenient(Int.self, .dueDay)
        isActive = c.lenient(Bool.self, .isActive)
    }

    /// "Cada mes" / "Cada 2 meses".
    public static func intervalLabel(_ months: Int?, language: AppLanguage = .current) -> String {
        let value = max(months ?? 1, 1)
        return value == 1 ? language.pick("Cada mes", "Every month") : language.pick("Cada \(value) meses", "Every \(value) months")
    }

    /// What it costs per month (the amount divided by its interval), like the Salvavidas counts it.
    public var monthlyAmount: Decimal? {
        guard let expectedAmount else { return nil }
        return expectedAmount / Decimal(max(intervalMonths ?? 1, 1))
    }
}

/// The body of a create (POST) or an edit (PUT). Only these fields are sent, so an edit keeps the
/// row's aliases, payment method and notes as stored.
public struct OwnerFixedExpenseRequest: Encodable, Sendable, Equatable {
    public static let intervals = [1, 2, 3, 6, 12]

    public let name: String
    public let category: String
    public let expectedAmount: Decimal
    public let intervalMonths: Int
    public let dueDay: Int?

    public init(name: String, category: String, expectedAmount: Decimal, intervalMonths: Int, dueDay: Int?) {
        self.name = name; self.category = category; self.expectedAmount = expectedAmount
        self.intervalMonths = intervalMonths; self.dueDay = dueDay
    }

    enum CodingKeys: String, CodingKey { case name, category, expectedAmount, intervalMonths, dueDay, frequency }

    /// Always `frequency: "monthly"` with `interval_months` (every N months), the shape the Owner's rows use.
    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(name, forKey: .name)
        try c.encode(category, forKey: .category)
        try c.encode(expectedAmount, forKey: .expectedAmount)
        try c.encode("monthly", forKey: .frequency)
        try c.encode(intervalMonths, forKey: .intervalMonths)
        if let dueDay { try c.encode(dueDay, forKey: .dueDay) }
    }

    /// The checks the form runs before sending: a name, an amount above zero, a known interval and a
    /// day from 1 to 31 when given. nil when valid, else the message to show.
    public static func problem(name: String, amount: Decimal?, intervalMonths: Int, dueDay: Int?, language: AppLanguage = .current) -> String? {
        if name.trimmingCharacters(in: .whitespaces).isEmpty { return language.pick("Escribí un nombre.", "Enter a name.") }
        guard let amount, amount > 0 else { return language.pick("Escribí un monto mayor que cero.", "Enter an amount above zero.") }
        if !intervals.contains(intervalMonths) { return language.pick("Elegí cada cuántos meses se paga.", "Choose how often it is paid.") }
        if let dueDay, !(1...31).contains(dueDay) { return language.pick("El día va de 1 a 31.", "The day goes from 1 to 31.") }
        return nil
    }
}

extension DincrService {
    /// The Owner's active fixed expenses. A read: it never writes.
    public func ownerFixedExpenses() async throws -> [OwnerFixedExpense] { try await client.get("/finance/fixed-expenses") }

    public func createOwnerFixedExpense(_ request: OwnerFixedExpenseRequest) async throws {
        try WriteContract.checkAmount(request.expectedAmount)
        let _: OwnerFixedExpenseAnswer = try await client.send("POST", "/finance/fixed-expenses", body: request)
    }

    public func updateOwnerFixedExpense(id: Int, _ request: OwnerFixedExpenseRequest) async throws {
        try WriteContract.checkAmount(request.expectedAmount)
        let _: OwnerFixedExpenseAnswer = try await client.send("PUT", "/finance/fixed-expenses/\(id)", body: request)
    }

    /// Removes it from the list (the backend deactivates the row; nothing else is deleted).
    public func removeOwnerFixedExpense(id: Int) async throws {
        let _: OwnerFixedExpenseAnswer = try await client.send("DELETE", "/finance/fixed-expenses/\(id)")
    }
}

/// Any JSON answer of a fixed-expense write (the row, or `{status, message, item}`).
struct OwnerFixedExpenseAnswer: Decodable {
    init(from decoder: Decoder) throws {}
}
