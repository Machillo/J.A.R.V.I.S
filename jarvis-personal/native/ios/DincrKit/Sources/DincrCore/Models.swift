import Foundation

// Client models for the DINCR API. They decode only the fields the native screens use and
// ignore everything else, so backend additions never break the app. Field names, types and
// optionality follow the FastAPI code (auth/saas.py enrich_identity,
// user_product/free_service.py); responses are not typed in OpenAPI yet, so each model is
// pinned by a fixture that mirrors what the backend builds (native/CONTRACT.md).

/// `GET /auth/me`
public struct Profile: Decodable, Sendable, Equatable {
    public struct Subscription: Decodable, Sendable, Equatable {
        public let plan: String?
        public let status: String?
        public let planName: String?
        /// `store`, `courtesy`, `promotion`…: how the plan was granted.
        public let accessSource: String?

        public init(plan: String?, status: String?, planName: String? = nil, accessSource: String? = nil) {
            self.plan = plan; self.status = status; self.planName = planName; self.accessSource = accessSource
        }
    }
    public struct Legal: Decodable, Sendable, Equatable {
        public let required: Bool?
        public let termsVersion: String?
        public let privacyVersion: String?
        public let acceptedAt: String?

        public init(required: Bool?, termsVersion: String?, privacyVersion: String?, acceptedAt: String? = nil) {
            self.required = required; self.termsVersion = termsVersion; self.privacyVersion = privacyVersion; self.acceptedAt = acceptedAt
        }
    }

    /// `allowed_users.id`: an integer, not the Supabase UUID.
    public let id: Int
    public let email: String?
    public let displayName: String?
    public let role: String?
    public let planSelected: Bool?
    public let profileSetupCompleted: Bool?
    public let baseCurrency: String?
    public let numberFormat: String?
    public let currencyPlacement: String?
    public let subscription: Subscription?
    public let legal: Legal?

    public init(
        id: Int, email: String? = nil, displayName: String? = nil, role: String? = "user",
        planSelected: Bool? = true, profileSetupCompleted: Bool? = true, baseCurrency: String? = "CRC",
        numberFormat: String? = "dot_comma", currencyPlacement: String? = "before",
        subscription: Subscription? = nil, legal: Legal? = nil
    ) {
        self.id = id; self.email = email; self.displayName = displayName; self.role = role
        self.planSelected = planSelected; self.profileSetupCompleted = profileSetupCompleted
        self.baseCurrency = baseCurrency; self.numberFormat = numberFormat
        self.currencyPlacement = currencyPlacement; self.subscription = subscription; self.legal = legal
    }

    /// A copy with some fields replaced (fixtures and gates; never a financial value).
    public func with(planSelected: Bool? = nil, subscription: Subscription? = nil, legal: Legal? = nil) -> Profile {
        Profile(id: id, email: email, displayName: displayName, role: role, planSelected: planSelected ?? self.planSelected,
                profileSetupCompleted: profileSetupCompleted, baseCurrency: baseCurrency, numberFormat: numberFormat,
                currencyPlacement: currencyPlacement, subscription: subscription ?? self.subscription, legal: legal ?? self.legal)
    }

    /// Owner/admin sessions are never served by the public app (Owner boundary).
    public var isOwner: Bool { role == "owner" || role == "admin" }
    public var plan: String { subscription?.plan ?? "free" }
    /// What the app offers; the backend still decides every request.
    public var planTier: PlanTier { PlanTier.from(subscription?.plan) }
    public var isCourtesy: Bool { subscription?.accessSource == "courtesy" }
    public var firstName: String? {
        let source = displayName ?? email?.split(separator: "@").first.map(String.init)
        return source?.split(separator: " ").first.map(String.init)
    }
}

/// One month of totals in `GET /user-product/free/dashboard`.
public struct MonthTotals: Decodable, Sendable, Equatable, Identifiable {
    public let month: String
    public let income: Decimal
    public let expenses: Decimal
    public let debtPaid: Decimal?
    public let balance: Decimal?
    public var id: String { month }

    public init(month: String, income: Decimal, expenses: Decimal, debtPaid: Decimal? = nil, balance: Decimal? = nil) {
        self.month = month; self.income = income; self.expenses = expenses; self.debtPaid = debtPaid; self.balance = balance
    }
}

public struct CategoryAmount: Decodable, Sendable, Equatable, Identifiable {
    public let category: String
    public let amount: Decimal
    public var id: String { category }
}

/// `GET /user-product/free/dashboard`
public struct FreeDashboard: Decodable, Sendable, Equatable {
    public let month: String
    public let income: Decimal
    public let expenses: Decimal
    public let debtPaid: Decimal?
    public let debtBalance: Decimal?
    public let balance: Decimal?
    public let availableAfterCommitments: Decimal?
    public let categories: [CategoryAmount]
    public let monthlyHistory: [MonthTotals]

    /// The key figure. The backend owns it; the client never derives it.
    public var available: Decimal? { availableAfterCommitments ?? balance }
}

/// A row of `GET /user-product/free/movements`.
public struct Movement: Decodable, Sendable, Equatable, Identifiable, Hashable {
    public enum Kind: String, Decodable, Sendable { case income, expense }

    public let movementId: String
    public let sourceId: Int?
    public let origin: String?
    public let transactionDate: String?
    public let description: String?
    public let amount: Decimal
    public let transactionType: Kind
    public let category: String?
    public let notes: String?
    public let editable: Bool
    /// Set when the amount was typed in, or received in, another currency (#269 manual entries,
    /// #273 mail transactions): `amount` is already in the base currency and these keep the typed
    /// figure and the user's rate.
    public let originalAmount: Decimal?
    public let originalCurrency: String?
    public let exchangeRate: Decimal?

    public var id: String { movementId }
    /// `YYYY-MM-DD` or nil when the backend has no usable date.
    public var day: String? { transactionDate.map { String($0.prefix(10)) } }

    public init(
        movementId: String, sourceId: Int? = nil, origin: String? = nil, transactionDate: String?,
        description: String?, amount: Decimal, transactionType: Kind, category: String?,
        notes: String? = nil, editable: Bool = true, originalAmount: Decimal? = nil, originalCurrency: String? = nil,
        exchangeRate: Decimal? = nil
    ) {
        self.movementId = movementId; self.sourceId = sourceId; self.origin = origin
        self.transactionDate = transactionDate; self.description = description; self.amount = amount
        self.transactionType = transactionType; self.category = category; self.notes = notes
        self.editable = editable; self.originalAmount = originalAmount; self.originalCurrency = originalCurrency
        self.exchangeRate = exchangeRate
    }

    /// Whether this app may edit or delete the row. The prototype does not edit currencies (it
    /// never sends `currency`/`exchange_rate`), and a `PUT` without them makes the backend store
    /// the row as a plain base-currency amount: `original_amount`, `original_currency` and
    /// `exchange_rate` would be erased by a change to the description alone. So any row carrying
    /// any of them stays read-only, whatever its currency. A row without a date is read-only too:
    /// the full-replacement `PUT` would have to invent one.
    public var isEditable: Bool {
        guard editable, originalAmount == nil, originalCurrency == nil, exchangeRate == nil, let day else { return false }
        let characters = Array(day)
        return characters.count == 10 && characters.indices.allSatisfy { index in
            index == 4 || index == 7 ? characters[index] == "-" : characters[index].isASCII && characters[index].isNumber
        }
    }

    enum CodingKeys: String, CodingKey {
        case movementId, sourceId, origin, transactionDate, description, amount, transactionType
        case category, notes, editable, originalAmount, originalCurrency, exchangeRate
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        movementId = try c.decode(String.self, forKey: .movementId)
        sourceId = try c.decodeIfPresent(Int.self, forKey: .sourceId)
        origin = try c.decodeIfPresent(String.self, forKey: .origin)
        transactionDate = try c.decodeIfPresent(String.self, forKey: .transactionDate)
        description = try c.decodeIfPresent(String.self, forKey: .description)
        amount = try c.decode(Decimal.self, forKey: .amount)
        // The backend sends only "income" or "expense" (debt payments arrive as read-only
        // "expense" rows); anything else is treated as money leaving.
        let rawType = try c.decodeIfPresent(String.self, forKey: .transactionType)
        transactionType = rawType == "income" ? .income : .expense
        category = try c.decodeIfPresent(String.self, forKey: .category)
        notes = try c.decodeIfPresent(String.self, forKey: .notes)
        editable = try c.decodeIfPresent(Bool.self, forKey: .editable) ?? false
        originalAmount = try c.decodeIfPresent(Decimal.self, forKey: .originalAmount)
        originalCurrency = try c.decodeIfPresent(String.self, forKey: .originalCurrency)
        exchangeRate = try c.decodeIfPresent(Decimal.self, forKey: .exchangeRate)
    }
}

/// Body of `POST /user-product/finance/income` and `/expenses` (OpenAPI: IncomeCreateRequest,
/// ExpenseCreateRequest).
public struct EntryCreate: Encodable, Sendable, Equatable {
    public let amount: Decimal
    public let description: String
    public let category: String
    public let entryDate: String?

    public init(amount: Decimal, description: String, category: String, entryDate: String?) {
        self.amount = amount; self.description = description; self.category = category; self.entryDate = entryDate
    }
}

/// Body of `PUT /user-product/free/movements/{id}` (OpenAPI: MovementUpdateRequest).
public struct MovementUpdate: Encodable, Sendable, Equatable {
    public let transactionDate: String
    public let description: String
    public let amount: Decimal
    public let transactionType: String
    public let category: String
    public let notes: String

    public init(transactionDate: String, description: String, amount: Decimal, transactionType: Movement.Kind, category: String, notes: String = "") {
        self.transactionDate = transactionDate; self.description = description; self.amount = amount
        self.transactionType = transactionType.rawValue; self.category = category; self.notes = notes
    }
}

/// Body of `POST /auth/profile-setup` (OpenAPI: ProfileSetupRequest).
public struct ProfileSetup: Encodable, Sendable, Equatable {
    public let displayName: String
    public let usageGoal: String
    public let baseCurrency: String
    public let enabledCurrencies: [String]
    public let numberFormat: String
    public let currencyPlacement: String
    public let selectedFinancialInstitutions: [String]

    public init(displayName: String, usageGoal: String, baseCurrency: String, enabledCurrencies: [String], numberFormat: String, currencyPlacement: String, selectedFinancialInstitutions: [String]) {
        self.displayName = displayName; self.usageGoal = usageGoal; self.baseCurrency = baseCurrency
        self.enabledCurrencies = enabledCurrencies; self.numberFormat = numberFormat
        self.currencyPlacement = currencyPlacement; self.selectedFinancialInstitutions = selectedFinancialInstitutions
    }
}

/// `POST /auth/profile-setup` returns the updated identity under `profile`.
public struct ProfileEnvelope: Decodable, Sendable {
    public let profile: Profile
}

/// Any JSON object. Create routes return the stored row; update and delete return
/// `{"status": "ok", "movement_id": ...}`. Nothing in them is needed.
public struct Acknowledgement: Decodable, Sendable {
    public let status: String?
}
