import Foundation

// The fixture backend's Atajos de iPhone routes (Debug demos and tests only), with the backend's shapes:
// - session routes (`/token`): VIP and the Owner, 403 otherwise; a shortcut token is not a session;
// - capture routes (`/apple-pay`, `/bank-sms`): only the current shortcut token (401 otherwise), a valid
//   `Idempotency-Key` (a repeat answers `already_received`), the plan (403) and the body (422).
// The token is invented and the captures are only counted (CLAUDE.md §4.F).
extension FixtureBackend {
    static let shortcutsPrefix = "/user-product/vip/shortcuts/"

    /// Number of captures received in this session (UI tests and unit tests).
    public var shortcutCaptureCount: Int { shortcutCaptures.count }

    func shortcutsRoute(_ request: URLRequest, method: String, path: String) -> Answer? {
        guard path.hasPrefix(Self.shortcutsPrefix) else { return nil }
        let bearer = request.value(forHTTPHeaderField: "Authorization")?.replacingOccurrences(of: "Bearer ", with: "") ?? ""
        let body = request.httpBody.flatMap { try? JSONSerialization.jsonObject(with: $0) as? [String: Any] } ?? [:]
        switch (method, path) {
        case (_, Self.shortcutsPrefix + "token"):
            // The app session only: a shortcut token never manages tokens.
            guard !bearer.hasPrefix("dsc_") else { return error(401, "Sesión inválida.") }
            if let denied = needs(.vip) { return denied }
            switch method {
            case "GET": return ok(["status": "ok", "linked": shortcutToken != nil, "created_at": shortcutToken == nil ? NSNull() as Any : "2026-10-28T12:00:00Z"])
            case "POST":
                let token = "dsc_fixture_\(nextId())"
                shortcutToken = token
                return (201, ["status": "ok", "token": token, "created_at": "2026-10-28T12:00:00Z"])
            case "DELETE":
                shortcutToken = nil
                return ok(["status": "ok", "linked": false])
            default: return error(405, "Method Not Allowed")
            }
        case ("POST", Self.shortcutsPrefix + "apple-pay"), ("POST", Self.shortcutsPrefix + "bank-sms"):
            guard let current = shortcutToken, bearer == current else { return error(401, "Atajo no vinculado.") }
            guard let key = request.value(forHTTPHeaderField: "Idempotency-Key"), ShortcutSender.isValidIdempotencyKey(key) else {
                return error(422, "Falta la clave de idempotencia.")
            }
            if let denied = needs(.vip) { return denied }
            if shortcutCaptures[key] != nil { return ok(["status": "already_received"]) }
            if path.hasSuffix("apple-pay") {
                let amount = body["amount"] as? String ?? ""
                let merchant = (body["merchant"] as? String ?? "").trimmingCharacters(in: .whitespaces)
                guard amount.range(of: #"^\d{1,10}(\.\d{1,2})?$"#, options: .regularExpression) != nil, (decimal(amount) ?? 0) > 0 else {
                    return error(422, "El monto no es válido.")
                }
                guard ["CRC", "USD"].contains(body["currency"] as? String ?? ""), (1...120).contains(merchant.count) else {
                    return error(422, "Revisá la moneda y el comercio.")
                }
                shortcutCaptures[key] = "created"
                return (201, ["status": "created"])
            }
            let text = (body["text"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            guard (1...1000).contains(text.count) else { return error(422, "El mensaje no es válido.") }
            // A stand-in for the parsers: a notice that mentions a purchase is recognized.
            let status = text.lowercased().contains("compra") ? "created" : "not_recognized"
            shortcutCaptures[key] = status
            return status == "created" ? (201, ["status": "created"]) : ok(["status": "not_recognized"])
        default:
            return error(404, "Not Found")
        }
    }
}
