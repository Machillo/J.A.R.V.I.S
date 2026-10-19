import Foundation

// App Store subscriptions (BIL-03), the same contract as Android's Google Play (`StoreBilling`): the
// backend is the only authority. Before buying, it issues a customer token that travels as the
// purchase's `appAccountToken`; after buying, the signed transaction is sent to
// `/product-ops/billing/store/apple/transactions`, which verifies Apple's signature and decides the
// plan. Prices only ever come from the store; the catalog names the products. Android: `OpsModels.kt`.

/// `GET /product-ops/billing/store/catalog`.
public struct StoreCatalog: Decodable, Sendable, Equatable {
    public struct Product: Decodable, Sendable, Equatable {
        public let productId: String?
        public init(productId: String?) { self.productId = productId }
    }
    public struct Plan: Decodable, Sendable, Equatable {
        public let code: String
        public let monthly: Product?
        public let annual: Product?
        public init(code: String, monthly: Product?, annual: Product?) { self.code = code; self.monthly = monthly; self.annual = annual }
    }
    public let plans: [Plan]

    public init(plans: [Plan]) { self.plans = plans }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        plans = try container.decodeIfPresent([Plan].self, forKey: .plans) ?? []
    }

    private enum CodingKeys: String, CodingKey { case plans }
}

/// `GET /product-ops/billing/store/entitlement`: the server's view of the store subscription.
public struct StoreEntitlement: Decodable, Sendable, Equatable {
    public let plan: String?
    public let status: String?
    public let provider: String?

    public init(plan: String?, status: String?, provider: String?) {
        self.plan = plan; self.status = status; self.provider = provider
    }

    /// A store subscription the server counts as live (`product_ops.store_billing.ACTIVE_STATES`).
    public var isLive: Bool {
        ["apple", "google"].contains(provider ?? "") && StoreEntitlement.liveStatuses.contains(status ?? "")
    }

    public static let liveStatuses: Set<String> = ["trialing", "active", "grace_period"]
}

public struct StoreCustomerToken: Decodable, Sendable, Equatable {
    public let token: String
}

struct AppleTransactionRequest: Encodable, Sendable {
    let signedTransaction: String
}

/// The answer of `/product-ops/billing/store/apple/transactions`.
public struct StoreVerification: Decodable, Sendable, Equatable {
    public let status: String?
    public let plan: String?
}

/// One subscription the screen can offer: the plan, its period and the store's product.
public struct StoreOffer: Sendable, Equatable, Identifiable {
    public enum Period: String, Sendable { case monthly, annual }
    public let plan: String
    public let period: Period
    public let productId: String
    public var id: String { productId }

    public init(plan: String, period: Period, productId: String) {
        self.plan = plan; self.period = period; self.productId = productId
    }

    /// Every product the catalog names, in its order (monthly before annual). Which of them the
    /// store actually sells (and at what price) is the store's answer, never this list's.
    public static func of(_ catalog: StoreCatalog) -> [StoreOffer] {
        catalog.plans.flatMap { plan in
            [(StoreOffer.Period.monthly, plan.monthly), (.annual, plan.annual)].compactMap { period, product in
                product?.productId.flatMap { $0.isEmpty ? nil : StoreOffer(plan: plan.code, period: period, productId: $0) }
            }
        }
    }
}

/// What to tell the user when the backend refuses a purchase (the same words as Android).
public enum StoreMessages {
    public static func verificationFailure(status: Int, language: AppLanguage = .current) -> String {
        switch status {
        case 409: language.pick("Esta compra pertenece a otra cuenta DINCR.", "This purchase belongs to another DINCR account.")
        case 422: language.pick("No pudimos verificar la compra con App Store.", "We couldn’t verify the purchase with the App Store.")
        case 503: language.pick("Las compras en la tienda están en pausa. Tu pago no se perdió: tocá Restaurar más tarde.",
                                "Store purchases are paused. Your payment isn’t lost: tap Restore later.")
        default: language.pick("No pudimos confirmar la compra. Tocá Restaurar.", "We couldn’t confirm the purchase. Tap Restore.")
        }
    }

    public static func alreadySubscribed(_ language: AppLanguage = .current) -> String {
        language.pick("Ya tenés una suscripción activa en la tienda.", "You already have an active store subscription.")
    }

    public static func pending(_ language: AppLanguage = .current) -> String {
        language.pick("Tu pago está pendiente. Te avisamos cuando App Store lo confirme.",
                      "Your payment is pending. We’ll update your plan when the App Store confirms it.")
    }

    public static func cancelled(_ language: AppLanguage = .current) -> String {
        language.pick("Compra cancelada.", "Purchase cancelled.")
    }

    public static func unavailable(_ language: AppLanguage = .current) -> String {
        language.pick("Las suscripciones de la tienda no están disponibles en esta versión de la app.",
                      "Store subscriptions aren’t available in this app version.")
    }
}
