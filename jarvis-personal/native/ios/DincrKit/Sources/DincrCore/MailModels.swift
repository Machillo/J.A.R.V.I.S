import Foundation

// Email Monitor (VIP): mailbox status, candidates detected in bank notices, review and account
// ownership. The backend reads the mailbox (Gmail read-only) and parses it deterministically;
// nothing is saved without the user's review, and a notice in another currency needs the user's
// own exchange rate. Same contract as Android `MailModels.kt` (native/CONTRACT.md).

/// `GET /user-product/vip/gmail/status`.
public struct MailStatus: Decodable, Sendable, Equatable {
    public struct Consent: Decodable, Sendable, Equatable {
        public let required: Bool?
        public let version: String?
        public init(required: Bool?, version: String?) { self.required = required; self.version = version }
    }

    public struct Connection: Decodable, Sendable, Equatable, Identifiable {
        public let id: Int
        public let provider: String?
        public let googleEmail: String?
        public let status: String?
        public let automaticUpdates: Bool?
        public let importSince: String?

        public init(id: Int, provider: String?, googleEmail: String?, status: String?, automaticUpdates: Bool? = nil, importSince: String? = nil) {
            self.id = id; self.provider = provider; self.googleEmail = googleEmail; self.status = status
            self.automaticUpdates = automaticUpdates; self.importSince = importSince
        }

        /// `active`, `reauthorization_required` or `disabled`.
        public var needsReconnect: Bool { status == "reauthorization_required" }
        public var isDisabled: Bool { status == "disabled" }
    }

    public let connected: Bool?
    public let needsReauthorization: Bool?
    public let pending: Int?
    public let microsoftAvailable: Bool?
    public let consent: Consent?
    public let connections: [Connection]?
    /// How long the backend keeps review evidence and mail metadata (configurable server-side).
    public let retention: Retention?

    public struct Retention: Decodable, Sendable, Equatable {
        public let reviewEvidenceDays: Int?
        public let emailMetadataDays: Int?
        public init(reviewEvidenceDays: Int?, emailMetadataDays: Int?) { self.reviewEvidenceDays = reviewEvidenceDays; self.emailMetadataDays = emailMetadataDays }
    }

    public init(connected: Bool?, needsReauthorization: Bool? = false, pending: Int? = nil, microsoftAvailable: Bool? = false,
                consent: Consent?, connections: [Connection]?, retention: Retention? = nil) {
        self.connected = connected; self.needsReauthorization = needsReauthorization; self.pending = pending
        self.microsoftAvailable = microsoftAvailable; self.consent = consent; self.connections = connections; self.retention = retention
    }

    public var isConnected: Bool { connected == true }
    /// Consent must be (re)accepted when the backend says so, or says nothing (fail closed).
    public var consentRequired: Bool { consent?.required ?? true }
    /// The mailboxes to show: `/status` also returns disconnected (disabled) rows.
    public var mailboxes: [Connection] { (connections ?? []).filter { !$0.isDisabled } }
}

public struct MailConsentRequest: Encodable, Sendable, Equatable {
    public let accepted: Bool
    public let version: String
    public init(version: String) { self.accepted = true; self.version = version }
}

/// Body of `POST /vip/gmail/connect` and `/vip/mail/microsoft/connect`.
public struct MailConnectRequest: Encodable, Sendable, Equatable {
    public enum Scope: String, Sendable, CaseIterable { case currentMonth = "current_month", currentYear = "current_year" }
    /// How far back the first scan reads.
    public let importScope: String
    /// The app language (`es`/`en`) for Google's consent screen (#288, `hl`). Microsoft ignores it.
    public let locale: String

    public init(scope: Scope, language: AppLanguage) {
        self.importScope = scope.rawValue; self.locale = language.rawValue
    }
}

public struct MailConnectResponse: Decodable, Sendable, Equatable {
    public let authorizationUrl: String
    public init(authorizationUrl: String) { self.authorizationUrl = authorizationUrl }
}

public struct MailCompleteRequest: Encodable, Sendable, Equatable {
    public let flow: String
    public let completion: String
    public init(flow: String, completion: String) { self.flow = flow; self.completion = completion }
}

public struct MailCompleteResponse: Decodable, Sendable, Equatable {
    public let status: String?
    public let provider: String?
    public let alreadyCompleted: Bool?
    public init(status: String?, provider: String?, alreadyCompleted: Bool?) {
        self.status = status; self.provider = provider; self.alreadyCompleted = alreadyCompleted
    }
}

/// `POST /user-product/vip/gmail/sync`.
public struct MailSyncResult: Decodable, Sendable, Equatable {
    public let status: String?
    public let found: Int?
    public let pending: Int?
    public let duplicates: Int?
    public let autoSaved: Int?
    public let scanScope: String?
    public let initialScanComplete: Bool?
    /// Ids of the mailboxes that failed (a list, not a count).
    public let failedConnections: [Int]?

    public init(status: String?, found: Int?, pending: Int?, duplicates: Int? = 0, autoSaved: Int? = 0, scanScope: String? = nil,
                initialScanComplete: Bool? = true, failedConnections: [Int]? = []) {
        self.status = status; self.found = found; self.pending = pending; self.duplicates = duplicates; self.autoSaved = autoSaved
        self.scanScope = scanScope; self.initialScanComplete = initialScanComplete; self.failedConnections = failedConnections
    }
}

/// `GET /user-product/vip/gmail/emails?status=`: `{status, items}` (at most 200, newest first).
public struct MailCandidateList: Decodable, Sendable, Equatable {
    public let items: [MailCandidate]?
    public init(items: [MailCandidate]?) { self.items = items }
}

/// A row of `GET /user-product/vip/gmail/emails`.
public struct MailCandidate: Decodable, Sendable, Equatable, Identifiable {
    public static let convertible: Set<String> = ["CRC", "USD"]

    public let candidateId: Int?
    public let emailId: Int?
    public let bank: String?
    public let sender: String?
    public let subject: String?
    public let receivedAt: String?
    public let description: String?
    public let amount: Decimal?
    public let currency: String?
    public let originalAmount: Decimal?
    public let originalCurrency: String?
    public let accountBaseCurrency: String?
    public let transactionDate: String?
    public let transactionType: String?
    public let category: String?
    public let reviewStatus: String?
    public let resolutionReason: String?
    public let isInternalTransfer: Bool?
    public let sourceType: String?

    public var id: String { candidateId.map { "c\($0)" } ?? "e\(emailId ?? 0)" }

    public init(candidateId: Int?, emailId: Int? = nil, bank: String?, sender: String? = nil, subject: String? = nil, receivedAt: String? = nil,
                description: String?, amount: Decimal?, currency: String?, originalAmount: Decimal? = nil, originalCurrency: String? = nil,
                accountBaseCurrency: String?, transactionDate: String?, transactionType: String?, category: String?,
                reviewStatus: String?, resolutionReason: String? = nil, isInternalTransfer: Bool? = false) {
        self.candidateId = candidateId; self.emailId = emailId; self.bank = bank; self.sender = sender; self.subject = subject
        self.receivedAt = receivedAt; self.description = description; self.amount = amount; self.currency = currency
        self.originalAmount = originalAmount; self.originalCurrency = originalCurrency; self.accountBaseCurrency = accountBaseCurrency
        self.transactionDate = transactionDate; self.transactionType = transactionType; self.category = category
        self.reviewStatus = reviewStatus; self.resolutionReason = resolutionReason; self.isInternalTransfer = isInternalTransfer
        self.sourceType = nil
    }

    /// The account's base currency; the backend uses CRC when it is unknown (`candidate_currency`).
    public var baseCurrency: String { accountBaseCurrency?.uppercased() ?? "CRC" }

    private var usesOriginal: Bool {
        guard let original = originalCurrency, !original.isEmpty, originalAmount != nil else { return false }
        return original.uppercased() != currency?.uppercased()
    }

    /// The money as the bank notice stated it. When the notice was in another currency the parser's
    /// converted `amount` is not trusted: the native pair is `(original_currency, original_amount)`.
    public var nativeCurrency: String? { usesOriginal ? originalCurrency?.uppercased() : currency?.uppercased() }
    public var nativeAmount: Decimal? { usesOriginal ? originalAmount : amount }

    public var isPending: Bool { reviewStatus == "pending" }

    /// Another convertible currency than the account's: accepting needs the user's own rate.
    public var needsRate: Bool {
        guard let native = nativeCurrency else { return false }
        let base = baseCurrency
        return native != base && Self.convertible.contains(native) && Self.convertible.contains(base)
    }

    /// A currency DINCR cannot convert: the notice can only be rejected.
    public var cannotConvert: Bool {
        guard let native = nativeCurrency else { return false }
        let base = baseCurrency
        return native != base && !(Self.convertible.contains(native) && Self.convertible.contains(base))
    }
}

/// Body of `PUT /vip/gmail/candidates/{id}/accept` (accept with corrections).
public struct CandidateCorrection: Encodable, Sendable, Equatable {
    public let transactionDate: String
    public let description: String
    /// In the notice's own currency.
    public let amount: Decimal
    public let transactionType: String
    /// Always sent: omitting it would reset the category to "general".
    public let category: String
    /// Colones per 1 dollar typed by the user; only when the notice is in another currency.
    public let exchangeRate: Decimal?

    public init(transactionDate: String, description: String, amount: Decimal, transactionType: String, category: String, exchangeRate: Decimal?) {
        self.transactionDate = transactionDate; self.description = description; self.amount = amount
        self.transactionType = transactionType; self.category = category; self.exchangeRate = exchangeRate
    }

    enum CodingKeys: String, CodingKey { case transactionDate, description, amount, transactionType, category, exchangeRate }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(transactionDate, forKey: .transactionDate)
        try c.encode(description, forKey: .description)
        try c.encode(amount, forKey: .amount)
        try c.encode(transactionType, forKey: .transactionType)
        try c.encode(category, forKey: .category)
        // Absent (not null) when the notice is in the account's currency.
        try c.encodeIfPresent(exchangeRate, forKey: .exchangeRate)
    }
}

/// Answer of accept / reject. `already_reviewed` means nothing changed now.
public struct CandidateReviewResult: Decodable, Sendable, Equatable {
    public let status: String?
    public let candidateId: Int?
    public let transactionId: Int?
    public let alreadyReviewed: Bool?
    public let isInternalTransfer: Bool?

    public init(status: String?, candidateId: Int?, transactionId: Int?, alreadyReviewed: Bool?, isInternalTransfer: Bool? = false) {
        self.status = status; self.candidateId = candidateId; self.transactionId = transactionId
        self.alreadyReviewed = alreadyReviewed; self.isInternalTransfer = isInternalTransfer
    }
}

/// `GET /user-product/vip/financial-identity`.
public struct FinancialIdentity: Decodable, Sendable, Equatable {
    public struct Account: Decodable, Sendable, Equatable, Identifiable {
        public let id: Int
        public let accountName: String?
        public let bankName: String?
        public let currency: String?
        public let accountLast4: String?
        public let ownershipStatus: String?

        public init(id: Int, accountName: String?, bankName: String?, currency: String?, accountLast4: String?, ownershipStatus: String?) {
            self.id = id; self.accountName = accountName; self.bankName = bankName; self.currency = currency
            self.accountLast4 = accountLast4; self.ownershipStatus = ownershipStatus
        }
    }
    public let items: [Account]?
    public init(items: [Account]?) { self.items = items }
}

public struct OwnershipRequest: Encodable, Sendable, Equatable {
    public let ownershipStatus: String
    /// `own` or `not_mine` (`financial_identity.confirm_financial_account`).
    public init(own: Bool) { self.ownershipStatus = own ? "own" : "not_mine" }
}

/// `GET /vip/gmail/own-transfer-suggestions`.
public struct OwnTransferSuggestions: Decodable, Sendable, Equatable {
    public struct Side: Decodable, Sendable, Equatable {
        public let candidateId: Int?
        public let bank: String?
        public let date: String?
        public let direction: String?
        public let amount: Decimal?
        public let currency: String?

        public init(candidateId: Int?, bank: String?, date: String?, direction: String?, amount: Decimal?, currency: String?) {
            self.candidateId = candidateId; self.bank = bank; self.date = date; self.direction = direction
            self.amount = amount; self.currency = currency
        }
    }
    public struct Pair: Decodable, Sendable, Equatable {
        public let first: Side?
        public let second: Side?
        public init(first: Side?, second: Side?) { self.first = first; self.second = second }
    }
    public let items: [Pair]?
    public init(items: [Pair]?) { self.items = items }
}

public struct OwnTransferRequest: Encodable, Sendable, Equatable {
    public static let cannotInfer = "?"
    public let counterpartId: Int
    public let confirmOwnedAccounts: Bool
    public let unknownDirection: String?

    public init(counterpartId: Int, unknownDirection: String?) {
        self.counterpartId = counterpartId; self.confirmOwnedAccounts = true; self.unknownDirection = unknownDirection
    }

    /// The direction to declare for the notice whose direction is unknown: money between the user's
    /// own accounts leaves one and enters the other, so it is the opposite of the known side (shown
    /// to the user before confirming). Nil when both are known; `cannotInfer` when neither is.
    public static func unknownDirection(first: String?, second: String?) -> String? {
        let known: Set<String> = ["in", "out"]
        let a = first.flatMap { known.contains($0) ? $0 : nil }
        let b = second.flatMap { known.contains($0) ? $0 : nil }
        switch (a, b) {
        case (.some, .some): return nil
        case let (.some(side), nil), let (nil, .some(side)): return side == "in" ? "out" : "in"
        case (nil, nil): return cannotInfer
        }
    }
}

/// A mail connection coming back from the provider (`<scheme>://gmail/callback?…`), same contract
/// as `frontend/src/lib/mailOAuth.js` and Android `MailReturn`. The backend finished the provider
/// exchange and parked the mailbox; `POST /vip/mail/oauth/complete {flow, completion}` attaches it,
/// and only the session that started the flow can do so.
public struct MailReturn: Sendable, Equatable {
    public enum Provider: String, Sendable { case gmail, microsoft }

    public let provider: Provider
    public let status: String
    public let flow: String?
    public let completion: String?
    public let ret: String?

    public var isAuthorized: Bool { status == "authorized" && !(flow ?? "").isEmpty && !(completion ?? "").isEmpty }
    /// Stable key for the handled ledger.
    public var key: String { "\(provider.rawValue):\(status):\(flow ?? ""):\(ret ?? "")" }

    /// Fails closed (nil) unless it is exactly `<scheme>://gmail/callback` for one of `schemes`,
    /// with no user, port or fragment, one provider status and no duplicated parameter.
    public static func parse(_ url: URL, schemes: Set<String>) -> MailReturn? {
        guard let parts = URLComponents(url: url, resolvingAgainstBaseURL: false),
              let scheme = parts.scheme?.lowercased(), schemes.contains(where: { $0.lowercased() == scheme }),
              parts.host?.lowercased() == "gmail", parts.path == "/callback",
              parts.user == nil, parts.password == nil, parts.port == nil, (parts.fragment ?? "").isEmpty else { return nil }
        let items = parts.queryItems ?? []
        for name in ["gmail", "microsoft", "flow", "completion", "ret"] where items.filter({ $0.name == name }).count > 1 { return nil }
        func single(_ name: String) -> String? { items.first { $0.name == name }.map { $0.value ?? "" } }
        let gmail = single("gmail"), microsoft = single("microsoft")
        let provider: Provider
        let status: String
        switch (gmail, microsoft) {
        case let (.some(value), nil): provider = .gmail; status = value
        case let (nil, .some(value)): provider = .microsoft; status = value
        default: return nil
        }
        guard !status.trimmingCharacters(in: .whitespaces).isEmpty, status.count <= 64 else { return nil }
        // Ledger keys and API bodies never carry control characters.
        let values = [status, single("flow"), single("completion"), single("ret")].compactMap { $0 }
        guard values.allSatisfy({ $0.unicodeScalars.allSatisfy { !CharacterSet.controlCharacters.contains($0) } }) else { return nil }
        return MailReturn(provider: provider, status: status, flow: single("flow").flatMap { $0.isEmpty ? nil : $0 },
                          completion: single("completion").flatMap { $0.isEmpty ? nil : $0 }, ret: single("ret"))
    }

    /// Copy for a provider status that is not a success.
    public static func message(_ status: String, language: AppLanguage) -> String {
        switch status {
        case "denied": language.pick("Cancelaste el permiso. Tu correo no se conectó.", "You declined the permission. Your mail was not connected.")
        case "invalid_state", "already_processed": language.pick("Ese enlace de conexión ya no es válido. Intentá conectar de nuevo.", "That connection link is no longer valid. Try connecting again.")
        case "vip_required": language.pick("Conectar tu correo es parte de VIP.", "Connecting your mail is part of VIP.")
        case "permission_missing": language.pick("Falta el permiso de solo lectura. Volvé a conectar y aceptá el permiso.", "The read-only permission is missing. Connect again and accept it.")
        case "mailbox_missing", "mailbox_unavailable": language.pick("No pudimos usar ese buzón. Probá con otra cuenta.", "We couldn’t use that mailbox. Try another account.")
        default: language.pick("No pudimos conectar tu correo. Intentá de nuevo.", "We couldn’t connect your mail. Please try again.")
        }
    }
}

/// Handled returns (last `capacity`), so a return delivered twice is redeemed once.
public struct HandledReturns: Sendable, Equatable {
    public private(set) var keys: [String]
    let capacity: Int

    public init(_ keys: [String] = [], capacity: Int = 50) {
        self.capacity = capacity
        self.keys = Array(keys.suffix(capacity))
    }

    public func contains(_ key: String) -> Bool { keys.contains(key) }

    public mutating func add(_ key: String) {
        guard !keys.contains(key) else { return }
        keys.append(key)
        if keys.count > capacity { keys.removeFirst(keys.count - capacity) }
    }
}
