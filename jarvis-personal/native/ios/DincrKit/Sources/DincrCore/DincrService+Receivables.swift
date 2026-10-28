import Foundation

// JARVIS → Control de dinero (Owner only: `/finance/*` is an Owner route and the backend refuses
// everyone else). The writes are explicit Owner commands and are never retried on their own: the
// backend does not deduplicate them.
extension DincrService {
    /// The people who owe the Owner money, for the current card cycle. A read: it never syncs or writes.
    public func receivables() async throws -> ReceivablesReport { try await client.get("/finance/receivables") }

    /// Records a payment the person made.
    public func recordReceivablePayment(id: Int, _ request: ReceivablePaymentRequest) async throws {
        try Self.check(try await client.send("POST", "/finance/receivables/\(id)/payments", body: request, as: ReceivableWriteResult.self))
    }

    /// Records money someone now owes the Owner (a new person is created by name).
    public func addReceivableEntry(_ request: ReceivableEntryRequest) async throws {
        try Self.check(try await client.send("POST", "/finance/receivables/entries", body: request, as: ReceivableWriteResult.self))
    }

    /// The cards the Owner marked as carried by someone else. A read.
    public func additionalCards() async throws -> AdditionalCardsList { try await client.get("/finance/additional-cards") }

    /// Marks a card as carried by `personName`; its pending purchase notices become that person's debt.
    @discardableResult
    public func saveAdditionalCard(last4: String, personName: String) async throws -> AdditionalCardResult {
        try await client.send("PUT", "/finance/additional-cards/\(last4)", body: AdditionalCardRequest(personName: personName))
    }

    /// The card is not additional any more: its settled purchases go back to review. Nothing is deleted.
    @discardableResult
    public func stopAdditionalCard(last4: String) async throws -> AdditionalCardResult {
        try await client.send("DELETE", "/finance/additional-cards/\(last4)")
    }

    /// The backend refuses these writes in the body with HTTP 200: shown as an error, never as saved.
    private static func check(_ result: ReceivableWriteResult) throws {
        guard result.succeeded else {
            throw APIError(kind: .validation, code: result.status ?? "", message: result.message ?? "No pudimos guardarlo.")
        }
    }
}
