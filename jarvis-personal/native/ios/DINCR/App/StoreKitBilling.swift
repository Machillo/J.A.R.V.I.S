import DincrCore
import Foundation
import StoreKit

/// BIL-03 — App Store subscriptions with StoreKit 2, the same contract as Android's `StoreBilling`
/// (Google Play): the backend is the only authority.
/// - Before buying, the backend issues a customer token that travels as the purchase's
///   `appAccountToken`, so the purchase belongs to this DINCR account.
/// - After buying, the transaction as Apple signed it (JWS) goes to
///   `/product-ops/billing/store/apple/transactions`; the backend verifies the signature and decides
///   the plan. The transaction is finished only after the backend accepted it, so a purchase the
///   backend never confirmed is offered again by StoreKit (restore, `Transaction.updates`).
/// - Prices only ever come from the store; the backend's catalog names the products.
@MainActor
final class StoreKitBilling {
    struct Offer: Identifiable, Equatable {
        let offer: StoreOffer
        /// The store's product, or nil when the store doesn't sell it to this build (not configured).
        let product: Product?
        var id: String { offer.id }
        var price: String? { product?.displayPrice }

        static func == (lhs: Offer, rhs: Offer) -> Bool { lhs.offer == rhs.offer && lhs.price == rhs.price }
    }

    enum Outcome: Equatable { case verified, pending, cancelled }

    struct Failure: LocalizedError {
        let message: String
        var errorDescription: String? { message }
    }

    private let service: DincrService
    private var updates: Task<Void, Never>?

    init(service: DincrService) { self.service = service }

    /// The catalog's products with the store's answer (price), in the catalog's order.
    func offers() async throws -> [Offer] {
        let wanted = StoreOffer.of(try await service.storeCatalog())
        let products = (try? await Product.products(for: wanted.map(\.productId))) ?? []
        let byID = Dictionary(products.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        return wanted.map { Offer(offer: $0, product: byID[$0.productId]) }
    }

    /// Buys `offer` for the signed-in account.
    func purchase(_ offer: Offer) async throws -> Outcome {
        guard let product = offer.product else { throw Failure(message: StoreMessages.unavailable()) }
        if try await service.storeEntitlement().isLive { throw Failure(message: StoreMessages.alreadySubscribed()) }
        let token = try await service.storeCustomerToken().token
        guard let account = UUID(uuidString: token) else { throw Failure(message: StoreMessages.verificationFailure(status: 0)) }
        switch try await product.purchase(options: [.appAccountToken(account)]) {
        case .success(let verification):
            try await deliver(verification)
            return .verified
        case .pending:
            return .pending
        case .userCancelled:
            return .cancelled
        @unknown default:
            return .cancelled
        }
    }

    /// Restore: asks the App Store for this Apple ID's purchases and sends every current one to the
    /// backend again. Returns how many were sent.
    func restore() async throws -> Int {
        try? await AppStore.sync()  // a cancelled sign-in still checks what this device knows
        var sent = 0
        for await verification in Transaction.currentEntitlements {
            try await deliver(verification)
            sent += 1
        }
        return sent
    }

    /// Transactions that arrive outside a purchase (renewals, Ask to Buy, another device) go to the
    /// backend as they come. Started once per signed-in session; stopped on sign-out.
    func observeUpdates() {
        guard updates == nil else { return }
        updates = Task { [weak self] in
            for await verification in Transaction.updates {
                try? await self?.deliver(verification)
            }
        }
    }

    func stopObserving() {
        updates?.cancel()
        updates = nil
    }

    private func deliver(_ verification: VerificationResult<Transaction>) async throws {
        do {
            _ = try await service.verifyAppleTransaction(signed: verification.jwsRepresentation)
        } catch let error as APIError {
            throw Failure(message: StoreMessages.verificationFailure(status: error.status))
        }
        await verification.unsafePayloadValue.finish()
    }
}
