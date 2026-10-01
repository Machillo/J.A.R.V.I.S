import Foundation

/// The Plan tab: exactly four rows, in this order (product decision; same on Android, `PlanHub.kt`).
/// Each keeps its historical plan gate; a row the plan does not include stays visible, locked, and
/// opens the plans screen. Debts and goals live on Home; budget, calendar and recurring items in
/// Profile → Finanzas. The Owner passes every gate by role (`Profile.planTier` is VIP for the
/// server's Owner role only); the backend still decides every request.
public enum PlanHubItem: String, CaseIterable, Sendable, Identifiable {
    case aguinaldo, strategy, salvavidas, distribution

    public var id: String { rawValue }

    /// Estrategia and Distribución: Basic (`strategy_basic`). Salvavidas: VIP (`strategy_vip`).
    /// Aguinaldo: VIP (`gmail_automation`).
    public var minimum: PlanTier {
        switch self {
        case .strategy, .distribution: .basic
        case .aguinaldo, .salvavidas: .vip
        }
    }

    /// The operational switch that pauses the row's backend route. The aguinaldo is paused with
    /// `vip_intelligence` (core/feature_flags.py), not with `gmail_automation`.
    public var killSwitch: OpsFlag? {
        switch self {
        case .aguinaldo, .salvavidas: .vipIntelligence
        case .strategy, .distribution: nil
        }
    }

    public enum Availability: Equatable, Sendable {
        case available
        /// Not in the plan: shown locked ("Disponible desde …"), opening the plans screen.
        case locked(PlanTier)
        case paused(OpsFlag)
    }

    public func availability(tier: PlanTier, flags: FeatureFlags) -> Availability {
        guard tier.rank >= minimum.rank else { return .locked(minimum) }
        if let killSwitch, !flags.isEnabled(killSwitch) { return .paused(killSwitch) }
        return .available
    }
}
