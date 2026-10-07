import Foundation

/// The Plan tab: exactly these rows, in this order (product decision; same on Android, `PlanHubScreen`).
/// Each keeps its historical plan gate; a row the plan does not include stays visible, locked, and
/// opens the plans screen. Debts are managed here (UX-4: Plan → Deudas; Home keeps a shortcut);
/// Ingresos y base holds the declared income and essential expenses (UX-7: every plan; with
/// Metas y ahorro → Tus ahorros it replaces the Situación screen);
/// goals live on Home; budget, calendar and recurring items in Profile → Finanzas. The Owner passes
/// every gate by role (`Profile.planTier` is VIP for the server's Owner role only); the backend
/// still decides every request.
public enum PlanHubItem: String, CaseIterable, Sendable, Identifiable {
    case aguinaldo, strategy, debts, incomeBase, salvavidas, distribution

    public var id: String { rawValue }

    /// Deudas: every plan (`debts`: everyone can record and keep their real debts). Ingresos y base:
    /// every plan (`finance_overview`: everyone declares their own reality).
    /// Estrategia and Distribución: Basic (`strategy_basic`). Salvavidas: VIP (`strategy_vip`).
    /// Aguinaldo: VIP (`gmail_automation`).
    public var minimum: PlanTier {
        switch self {
        case .debts, .incomeBase: .free
        case .strategy, .distribution: .basic
        case .aguinaldo, .salvavidas: .vip
        }
    }

    /// The operational switch that pauses the row's backend route. The aguinaldo is paused with
    /// `vip_intelligence` (core/feature_flags.py), not with `gmail_automation`.
    public var killSwitch: OpsFlag? {
        switch self {
        case .aguinaldo, .salvavidas: .vipIntelligence
        case .strategy, .debts, .incomeBase, .distribution: nil
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
