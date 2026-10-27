import Foundation

/// "Pagado con" for manual expenses, with the backend's rules (`expense_account`): only the user's
/// own accounts and cards, a request without the key leaves the link as it is, null clears it.
extension FixtureBackend {
    enum PaidWithLink {
        case keep
        /// An account id, or `NSNull()` to clear.
        case set(Any)
        case refused(Answer)
    }

    func paidWithOptions() -> [String: Any] {
        let own = identityAccounts.filter { $0["ownership_status"] as? String == "own" }
            .sorted { ($0["account_type"] as? String == "credit_card" ? 0 : 1) < ($1["account_type"] as? String == "credit_card" ? 0 : 1) }
        return ["status": "ok", "available": true, "items": own]
    }

    func paidWithLink(_ body: [String: Any]) -> PaidWithLink {
        guard let value = body["financial_account_id"] else { return .keep }
        if value is NSNull { return .set(NSNull()) }
        guard let id = value as? Int, let account = identityAccounts.first(where: { $0["id"] as? Int == id }) else {
            return .refused(error(404, "Cuenta financiera no encontrada."))
        }
        guard account["ownership_status"] as? String == "own" else { return .refused(error(409, "Confirmá primero que la cuenta es tuya.")) }
        return .set(id)
    }
}
