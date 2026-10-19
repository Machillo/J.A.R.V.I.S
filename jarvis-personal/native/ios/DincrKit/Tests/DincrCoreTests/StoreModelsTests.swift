import Foundation
import Testing
@testable import DincrCore

/// BIL-03 — the App Store side of the store contract: the catalog decodes the backend's shape, every
/// product it names becomes an offer (the store decides which are sold and at what price), a store
/// subscription is live exactly in the backend's states, and the backend's refusals read the same
/// as on Android. Synthetic data.
@Suite struct StoreModelsTests {
    private let catalogJSON = #"""
    {"currency":"CRC","trial_days":7,
     "plans":[{"code":"basic","monthly":{"price_crc":2990,"product_id":"finva.basic.monthly"},"annual":{"price_crc":29900,"product_id":"finva.basic.annual"}},
              {"code":"vip","monthly":{"price_crc":4990,"product_id":"finva.vip.monthly"},"annual":{"product_id":""}}],
     "stores":{"apple":{"ready":false,"billing":"App Store"}}}
    """#

    @Test func theCatalogNamesTheProductsAndNeverAPrice() throws {
        let catalog = try APIClient.decoder.decode(StoreCatalog.self, from: Data(catalogJSON.utf8))
        let offers = StoreOffer.of(catalog)
        #expect(offers.map(\.productId) == ["finva.basic.monthly", "finva.basic.annual", "finva.vip.monthly"],
                "every named product, in order; an empty id is not a product")
        #expect(offers.map(\.plan) == ["basic", "basic", "vip"])
        #expect(offers.map(\.period) == [.monthly, .annual, .monthly])
    }

    @Test func anEmptyCatalogOffersNothing() throws {
        #expect(StoreOffer.of(try APIClient.decoder.decode(StoreCatalog.self, from: Data("{}".utf8))).isEmpty)
    }

    @Test func aStoreSubscriptionIsLiveExactlyInTheBackendsStates() {
        for status in ["trialing", "active", "grace_period"] {
            #expect(StoreEntitlement(plan: "vip", status: status, provider: "apple").isLive, "\(status)")
            #expect(StoreEntitlement(plan: "vip", status: status, provider: "google").isLive, "\(status)")
        }
        for status in ["free", "expired", "revoked", "cancel_requested", "grace", "paused"] {
            #expect(!StoreEntitlement(plan: "vip", status: status, provider: "apple").isLive, "\(status)")
        }
        #expect(!StoreEntitlement(plan: "vip", status: "active", provider: nil).isLive, "a courtesy or Owner plan is not a store subscription")
        #expect(!StoreEntitlement(plan: "vip", status: "active", provider: "sandbox").isLive)
    }

    @Test func theBackendsRefusalsReadTheSameAsOnAndroid() {
        #expect(StoreMessages.verificationFailure(status: 409, language: .spanish) == "Esta compra pertenece a otra cuenta DINCR.")
        #expect(StoreMessages.verificationFailure(status: 422, language: .spanish) == "No pudimos verificar la compra con App Store.")
        #expect(StoreMessages.verificationFailure(status: 503, language: .spanish)
                == "Las compras en la tienda están en pausa. Tu pago no se perdió: tocá Restaurar más tarde.")
        #expect(StoreMessages.verificationFailure(status: 500, language: .spanish) == "No pudimos confirmar la compra. Tocá Restaurar.")
    }

    @Test func theFixtureAnswersTheStoreRoutesOnlyWhenAsked() async throws {
        let on = FixtureBackend.service(FixtureBackend(scenario: .populated, latency: .zero, storeBillingOn: true))
        #expect(try await on.featureFlags().isEnabled(.storeBilling))
        #expect(StoreOffer.of(try await on.storeCatalog()).count == 4)
        #expect(!(try await on.storeEntitlement().isLive))
        #expect(UUID(uuidString: try await on.storeCustomerToken().token) != nil, "a token the purchase can carry as appAccountToken")
        let off = FixtureBackend.service(FixtureBackend(scenario: .populated, latency: .zero))
        #expect(!(try await off.featureFlags().isEnabled(.storeBilling)))
    }
}
