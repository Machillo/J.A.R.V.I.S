import Foundation

// Account, plan and operations contracts: legal acceptance, plans and feature flags. Same shapes
// as Android `OpsModels.kt` (native/CONTRACT.md). Keys are snake_case on the wire; the client's
// encoder and decoder convert them.

/// `POST /auth/legal/accept`. The versions are the ones `/auth/me` asked for, never invented.
public struct LegalAcceptRequest: Encodable, Sendable, Equatable {
    public let acceptTerms: Bool
    public let acceptPrivacy: Bool
    public let termsVersion: String
    public let privacyVersion: String

    public init(termsVersion: String, privacyVersion: String) {
        self.acceptTerms = true; self.acceptPrivacy = true
        self.termsVersion = termsVersion; self.privacyVersion = privacyVersion
    }
}

public struct LegalAcceptResult: Decodable, Sendable, Equatable {
    public let status: String?
    public let required: Bool?

    public init(status: String?, required: Bool?) { self.status = status; self.required = required }
}

public struct Promotion: Decodable, Sendable, Equatable {
    public let code: String?
    public let active: Bool?
    public let endsAt: String?
    public let message: String?

    public init(code: String? = nil, active: Bool?, endsAt: String? = nil, message: String? = nil) {
        self.code = code; self.active = active; self.endsAt = endsAt; self.message = message
    }
}

/// An item of `GET /auth/plans`.
public struct PlanOption: Decodable, Sendable, Equatable, Identifiable {
    public let code: String
    public let name: String?
    public let tagline: String?
    public let features: [String]?
    public let regularPriceCrc: Int?
    public let promotion: Promotion?
    public var id: String { code }

    public init(code: String, name: String?, tagline: String? = nil, features: [String]? = nil, regularPriceCrc: Int? = nil, promotion: Promotion? = nil) {
        self.code = code; self.name = name; self.tagline = tagline; self.features = features
        self.regularPriceCrc = regularPriceCrc; self.promotion = promotion
    }
}

/// `GET /product-ops/billing/catalog`.
public struct BillingCatalog: Decodable, Sendable, Equatable {
    public struct CatalogPlan: Decodable, Sendable, Equatable {
        public let code: String
        public let regularPriceCrc: Int?
    }
    public let plans: [CatalogPlan]?
    public let promotion: Promotion?
    public let notice: String?

    public init(plans: [CatalogPlan]?, promotion: Promotion?, notice: String?) {
        self.plans = plans; self.promotion = promotion; self.notice = notice
    }
}

/// Paid plans can be chosen only while the launch promotion is active; otherwise they arrive
/// through the stores (Android: `PlanChooserScreen`).
public enum PlanOffer {
    public static func promotionActive(options: [PlanOption], catalog: BillingCatalog?) -> Bool {
        catalog?.promotion?.active == true || options.contains { $0.promotion?.active == true }
    }

    public static func canChoose(_ option: PlanOption, promotionActive: Bool) -> Bool {
        option.code == PlanTier.free.rawValue || promotionActive
    }
}

/// `POST /auth/plan`. `consentVersion` is the backend default (auth/models.py).
public struct PlanChangeRequest: Encodable, Sendable, Equatable {
    public static let consentVersion = "regular-2027-v1"
    public let plan: String
    public let acceptBetaTerms: Bool
    public let consentVersion: String

    public init(plan: String) {
        self.plan = plan; self.acceptBetaTerms = false; self.consentVersion = Self.consentVersion
    }
}

/// ok | plan_kept | downgrade_scheduled | promotion_active.
public struct PlanChangeResult: Decodable, Sendable, Equatable {
    public let status: String?
    public let plan: String?
    public let pendingPlan: String?
    public let effectiveAt: String?
    public let message: String?
    public let profile: Profile?

    public init(status: String?, plan: String?, pendingPlan: String?, effectiveAt: String?, message: String?, profile: Profile?) {
        self.status = status; self.plan = plan; self.pendingPlan = pendingPlan; self.effectiveAt = effectiveAt
        self.message = message; self.profile = profile
    }
}

/// `GET /product-ops/feature-flags`.
public struct FeatureFlags: Decodable, Sendable, Equatable {
    public struct Flag: Decodable, Sendable, Equatable {
        public let flagKey: String
        public let enabled: Bool?
        public let disabledMessageEs: String?
        public let disabledMessageEn: String?

        public init(flagKey: String, enabled: Bool?, disabledMessageEs: String? = nil, disabledMessageEn: String? = nil) {
            self.flagKey = flagKey; self.enabled = enabled
            self.disabledMessageEs = disabledMessageEs; self.disabledMessageEn = disabledMessageEn
        }
    }
    public let flags: [Flag]?

    public init(flags: [Flag]?) { self.flags = flags }

    /// Nothing loaded yet: every flag at its safe default.
    public static let unknown = FeatureFlags(flags: nil)

    /// A flag's state; unknown (missing, or flags not loaded) is the backend's safe default.
    public func isEnabled(_ flag: OpsFlag) -> Bool {
        flags?.first { $0.flagKey == flag.rawValue }?.enabled ?? flag.safeDefault
    }

    public func message(_ flag: OpsFlag, language: AppLanguage) -> String? {
        guard let entry = flags?.first(where: { $0.flagKey == flag.rawValue }) else { return nil }
        return language == .spanish ? entry.disabledMessageEs : entry.disabledMessageEn
    }
}

/// `GET /product-ops/health`.
public struct ServiceHealth: Decodable, Sendable, Equatable {
    public let status: String?
    public let activeIncidents: Int?
    public init(status: String?, activeIncidents: Int? = 0) { self.status = status; self.activeIncidents = activeIncidents }
}

/// `GET /product-ops/release-policy?platform=ios&version=` (fail-open).
public struct ReleasePolicy: Decodable, Sendable, Equatable {
    public let status: String?
    public let required: Bool?
    public let active: Bool?
    public let latestVersion: String?
    public let updateUrl: String?
    public let messageEs: String?
    public let messageEn: String?

    public init(status: String?, required: Bool?, active: Bool?, latestVersion: String? = nil, updateUrl: String? = nil, messageEs: String? = nil, messageEn: String? = nil) {
        self.status = status; self.required = required; self.active = active; self.latestVersion = latestVersion
        self.updateUrl = updateUrl; self.messageEs = messageEs; self.messageEn = messageEn
    }

    public var isRequired: Bool { active == true && (required == true || status == "required") }
    public var isOptional: Bool { active == true && !isRequired && status == "optional" }
    public func message(_ language: AppLanguage) -> String? { language == .spanish ? messageEs : messageEn }
}

/// A support ticket (`GET /product-ops/feedback`).
public struct SupportTicket: Decodable, Sendable, Equatable, Identifiable {
    public let id: Int
    public let category: String?
    public let subject: String?
    public let status: String?
    public let userResolution: String?
    public let createdAt: String?
    public let publicId: String?

    public init(id: Int, category: String?, subject: String?, status: String?, userResolution: String? = nil, createdAt: String? = nil, publicId: String? = nil) {
        self.id = id; self.category = category; self.subject = subject; self.status = status
        self.userResolution = userResolution; self.createdAt = createdAt; self.publicId = publicId
    }
}

/// `POST /product-ops/feedback`.
public struct SupportRequest: Encodable, Sendable, Equatable {
    public static let categories = ["error", "improvement", "payment", "account", "other"]
    public let category: String
    public let subject: String
    public let message: String
    public let appVersion: String?
    public let screen: String?

    public init(category: String, subject: String, message: String, appVersion: String?, screen: String? = "support") {
        self.category = category; self.subject = subject; self.message = message; self.appVersion = appVersion; self.screen = screen
    }
}

public struct SupportCreated: Decodable, Sendable, Equatable {
    public let id: Int?
    public let publicId: String?
    public init(id: Int?, publicId: String?) { self.id = id; self.publicId = publicId }
}

public struct ResolutionRequest: Encodable, Sendable, Equatable {
    public let resolution: String
    public init(resolved: Bool) { self.resolution = resolved ? "resolved" : "not_resolved" }
}
