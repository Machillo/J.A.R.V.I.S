import DincrCore
import StoreKit
import UIKit

/// Counts saved movements on this device and, when `RatingPrompt` says so, asks iOS for its own
/// rating dialog. Nothing leaves the phone. Fixtures and the Owner are never asked.
@MainActor
enum RatingRequest {
    private static let firstOpenKey = "dincr.rating.firstOpen"
    private static let savesKey = "dincr.rating.saves"
    private static let lastAskedKey = "dincr.rating.lastAsked"

    static func movementSaved(model: AppModel) {
        guard !model.environment.isFixtures, model.profile?.role != "owner" else { return }
        let defaults = UserDefaults.standard
        let now = Date()
        let firstOpen = defaults.object(forKey: firstOpenKey) as? Date ?? now
        defaults.set(firstOpen, forKey: firstOpenKey)
        let saves = defaults.integer(forKey: savesKey) + 1
        defaults.set(saves, forKey: savesKey)
        let lastAsked = defaults.object(forKey: lastAskedKey) as? Date
        guard RatingPrompt.shouldAsk(firstOpen: firstOpen, saves: saves, lastAsked: lastAsked, now: now) else { return }
        guard let scene = UIApplication.shared.connectedScenes.first(where: { $0.activationState == .foregroundActive }) as? UIWindowScene else { return }
        defaults.set(now, forKey: lastAskedKey)
        Task {
            try? await Task.sleep(for: .seconds(1)) // After the editor has closed.
            AppStore.requestReview(in: scene)
        }
    }
}
