import Foundation

// The two routes the background App Intents call (Shortcuts automations *Transacción* and *Mensaje*).
// They carry NO app session: only the limited shortcut token (`Authorization: Bearer dsc_…`) and an
// `Idempotency-Key`. Each creates a PENDING candidate in Movimientos → Por revisar; nothing is recorded
// until the user reviews it. Never log the token, the amount, the merchant, the card or the SMS text.

/// `POST /user-product/vip/shortcuts/apple-pay`.
public struct ShortcutPurchase: Encodable, Sendable, Equatable {
    public static let merchantLimit = 120
    public static let cardLimit = 60

    /// Canonical decimal string (`ShortcutAmount.wire`), never a float.
    public let amount: String
    public let currency: ShortcutCurrency
    public let merchant: String
    public let card: String?

    /// Trims the texts; a merchant or card longer than the backend admits is cut, an empty card is none.
    public init(amount: ShortcutAmount, merchant: String, card: String?) {
        self.amount = amount.wire
        self.currency = amount.currency
        self.merchant = String(merchant.trimmingCharacters(in: .whitespacesAndNewlines).prefix(Self.merchantLimit))
        let card = (card ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        self.card = card.isEmpty ? nil : String(card.prefix(Self.cardLimit))
    }

    enum CodingKeys: String, CodingKey { case amount, currency, merchant, card }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(amount, forKey: .amount)
        try container.encode(currency, forKey: .currency)
        try container.encode(merchant, forKey: .merchant)
        // The contract names the field: an absent card is an explicit null.
        if let card { try container.encode(card, forKey: .card) } else { try container.encodeNil(forKey: .card) }
    }
}

/// `POST /user-product/vip/shortcuts/bank-sms`.
public struct ShortcutBankMessage: Encodable, Sendable, Equatable {
    public static let limit = 1000
    public let text: String
    public init(text: String) { self.text = text.trimmingCharacters(in: .whitespacesAndNewlines) }
}

/// What the backend did with a send.
public enum ShortcutCaptureResult: Sendable, Equatable {
    case created, alreadyReceived
    /// Bank SMS only: the format is not supported yet. Not an error.
    case notRecognized

    public func purchaseMessage(_ language: AppLanguage = .current) -> String {
        switch self {
        case .created: language.pick("Compra enviada a DINCR para revisar.", "Purchase sent to DINCR for review.")
        case .alreadyReceived: language.pick("Ya la habíamos recibido.", "We already had it.")
        case .notRecognized: language.pick("DINCR no reconoció esta compra.", "DINCR didn’t recognize this purchase.")
        }
    }

    public func bankMessageMessage(_ language: AppLanguage = .current) -> String {
        switch self {
        case .created: language.pick("Aviso enviado a DINCR para revisar.", "Notice sent to DINCR for review.")
        case .alreadyReceived: language.pick("Ya lo habíamos recibido.", "We already had it.")
        case .notRecognized: language.pick("DINCR no reconoció este aviso.", "DINCR didn’t recognize this notice.")
        }
    }
}

/// A send that did not reach the review inbox, with a message safe to show (no internals).
public enum ShortcutCaptureError: Error, Sendable, Equatable {
    /// This iPhone holds no token: the user has not activated Atajos de iPhone.
    case notLinked
    /// 401: the token was revoked or replaced.
    case tokenRejected
    /// 403: the plan does not include it.
    case planNotIncluded
    /// The intent's own input (amount, merchant, text) is not valid.
    case invalidInput(String)
    /// 422: the backend's Spanish `detail` (shown to Spanish sessions only), or nil.
    case rejected(String?)
    /// 429.
    case tooMany
    case offline
    case server

    public enum Kind: Sendable { case purchase, bankMessage }

    public func message(_ kind: Kind, _ language: AppLanguage = .current) -> String {
        let t = language.pick
        switch self {
        case .notLinked, .tokenRejected:
            return t("Activá Atajos de iPhone en DINCR → Perfil.", "Turn on iPhone Shortcuts in DINCR → Profile.")
        case .planNotIncluded:
            return t("Tu plan no incluye Atajos de iPhone.", "Your plan doesn’t include iPhone Shortcuts.")
        case .invalidInput(let message):
            return message
        case .rejected(let detail):
            if language == .spanish, let detail, !detail.isEmpty { return detail }
            return t("DINCR no aceptó estos datos. Revisá el atajo.", "DINCR didn’t accept this data. Check the shortcut.")
        case .tooMany:
            return t("Demasiados envíos seguidos. Intentá de nuevo en un momento.", "Too many sends in a row. Try again in a moment.")
        case .offline:
            return kind == .purchase
                ? t("No pudimos enviar la compra. Revisá tu conexión.", "We couldn’t send the purchase. Check your connection.")
                : t("No pudimos enviar el aviso. Revisá tu conexión.", "We couldn’t send the notice. Check your connection.")
        case .server:
            return t("DINCR no pudo recibirlo ahora. Intentá de nuevo en unos minutos.", "DINCR couldn’t receive it now. Try again in a few minutes.")
        }
    }
}

/// Sends to the two shortcut routes with the shortcut token only (no `APIClient`, so no session token
/// can ever be attached). Redirects are refused (`URLSessionTransport`), so the token never goes to
/// another URL. A transient failure is retried once with the SAME `Idempotency-Key`: the backend
/// answers `already_received` if the first attempt had arrived.
public struct ShortcutSender: Sendable {
    static let purchasePath = "/user-product/vip/shortcuts/apple-pay"
    static let bankMessagePath = "/user-product/vip/shortcuts/bank-sms"
    static let retryableStatus: Set<Int> = [502, 503, 504]

    let baseURL: URL
    let transport: HTTPTransport
    let language: AppLanguage
    let timeout: TimeInterval
    let backoff: @Sendable () async -> Void

    public init(baseURL: URL, transport: HTTPTransport = URLSessionTransport(), language: AppLanguage = .current, timeout: TimeInterval = 15,
                backoff: @escaping @Sendable () async -> Void = { try? await Task.sleep(for: .seconds(1)) }) {
        self.baseURL = baseURL; self.transport = transport; self.language = language; self.timeout = timeout; self.backoff = backoff
    }

    /// A fresh key per run (a UUID: 36 characters of `[A-Za-z0-9-]`).
    public static func newIdempotencyKey() -> String { UUID().uuidString }

    /// The backend's rule: 8–128 characters of `[A-Za-z0-9_-]`.
    public static func isValidIdempotencyKey(_ key: String) -> Bool {
        (8...128).contains(key.count) && key.unicodeScalars.allSatisfy { $0.isASCII && (CharacterSet.alphanumerics.contains($0) || $0 == "-" || $0 == "_") }
    }

    public func send(_ purchase: ShortcutPurchase, token: String, idempotencyKey: String) async throws(ShortcutCaptureError) -> ShortcutCaptureResult {
        try await post(Self.purchasePath, body: purchase, token: token, idempotencyKey: idempotencyKey)
    }

    public func send(_ message: ShortcutBankMessage, token: String, idempotencyKey: String) async throws(ShortcutCaptureError) -> ShortcutCaptureResult {
        try await post(Self.bankMessagePath, body: message, token: token, idempotencyKey: idempotencyKey)
    }

    func request(_ path: String, body: Data, token: String, idempotencyKey: String) -> URLRequest {
        var request = URLRequest(url: baseURL.appending(path: path), timeoutInterval: timeout)
        request.httpMethod = "POST"
        request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(language.rawValue, forHTTPHeaderField: "Accept-Language")
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue(idempotencyKey, forHTTPHeaderField: "Idempotency-Key")
        return request
    }

    private func post<Body: Encodable>(_ path: String, body: Body, token: String, idempotencyKey: String) async throws(ShortcutCaptureError) -> ShortcutCaptureResult {
        guard ShortcutCredential.isValidToken(token) else { throw .notLinked }
        guard Self.isValidIdempotencyKey(idempotencyKey) else { throw .server }
        let data: Data
        do { data = try APIClient.encoder.encode(body) } catch { throw .server }
        let request = request(path, body: data, token: token, idempotencyKey: idempotencyKey)
        var attempt = 0
        while true {
            let answer: Data
            let response: HTTPURLResponse
            do {
                (answer, response) = try await transport.send(request)
            } catch {
                if let error = error as? URLError, error.code != .cancelled, APIClient.isTransient(error), attempt == 0 {
                    attempt += 1; await backoff(); continue
                }
                throw .offline
            }
            if Self.retryableStatus.contains(response.statusCode), attempt == 0 {
                attempt += 1; await backoff(); continue
            }
            return try Self.result(status: response.statusCode, body: answer)
        }
    }

    /// The backend's answer as a result or an error.
    static func result(status: Int, body: Data) throws(ShortcutCaptureError) -> ShortcutCaptureResult {
        let object = (try? JSONSerialization.jsonObject(with: body)) as? [String: Any]
        switch status {
        case 200, 201:
            switch object?["status"] as? String {
            case "created": return .created
            case "already_received": return .alreadyReceived
            case "not_recognized": return .notRecognized
            default:
                if status == 201 { return .created }
                throw .server
            }
        case 401: throw .tokenRejected
        case 403: throw .planNotIncluded
        case 409, 422:
            throw .rejected(object?["detail"] as? String)
        case 429: throw .tooMany
        default: throw .server
        }
    }
}

/// What one App Intent run does: read the token from the Keychain, validate the input, send it, and
/// forget a token the backend no longer accepts.
public struct ShortcutCaptureClient: Sendable {
    let store: ShortcutTokenStore
    let sender: ShortcutSender
    let language: AppLanguage

    public init(store: ShortcutTokenStore, sender: ShortcutSender, language: AppLanguage = .current) {
        self.store = store; self.sender = sender; self.language = language
    }

    public func registerPurchase(amount amountText: String, currency fallback: ShortcutCurrency, merchant: String, card: String?,
                                 idempotencyKey: String = ShortcutSender.newIdempotencyKey()) async throws(ShortcutCaptureError) -> ShortcutCaptureResult {
        guard let credential = store.read() else { throw .notLinked }
        let amount: ShortcutAmount
        switch ShortcutAmount.parse(amountText, fallback: fallback) {
        case .success(let parsed): amount = parsed
        case .failure(let failure): throw .invalidInput(failure.message(language))
        }
        let purchase = ShortcutPurchase(amount: amount, merchant: merchant, card: card)
        guard !purchase.merchant.isEmpty else {
            throw .invalidInput(language.pick("Falta el comercio de la compra.", "The purchase’s merchant is missing."))
        }
        return try await forgettingRejected { () throws(ShortcutCaptureError) in
            try await sender.send(purchase, token: credential.token, idempotencyKey: idempotencyKey)
        }
    }

    public func sendBankMessage(_ text: String, idempotencyKey: String = ShortcutSender.newIdempotencyKey()) async throws(ShortcutCaptureError) -> ShortcutCaptureResult {
        guard let credential = store.read() else { throw .notLinked }
        let message = ShortcutBankMessage(text: text)
        guard !message.text.isEmpty else {
            throw .invalidInput(language.pick("Falta el texto del mensaje.", "The message text is missing."))
        }
        guard message.text.count <= ShortcutBankMessage.limit else {
            throw .invalidInput(language.pick("El mensaje es demasiado largo para un aviso bancario.", "The message is too long for a bank notice."))
        }
        return try await forgettingRejected { () throws(ShortcutCaptureError) in
            try await sender.send(message, token: credential.token, idempotencyKey: idempotencyKey)
        }
    }

    /// A revoked or replaced token (401) is forgotten here, so Perfil shows "No vinculado".
    private func forgettingRejected(_ send: () async throws(ShortcutCaptureError) -> ShortcutCaptureResult) async throws(ShortcutCaptureError) -> ShortcutCaptureResult {
        do {
            return try await send()
        } catch {
            if error == .tokenRejected { store.clear() }
            throw error
        }
    }
}
