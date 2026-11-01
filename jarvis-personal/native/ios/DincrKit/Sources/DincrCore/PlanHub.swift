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
    case aguinaldo, strategy, debts, incomeBase, fixedExpenses, salvavidas, retirement, projections, scenarios, distribution

    public var id: String { rawValue }

    /// Deudas: every plan (`debts`: everyone can record and keep their real debts). Ingresos y base:
    /// every plan (`finance_overview`: everyone declares their own reality).
    /// Estrategia and Distribución: Basic (`strategy_basic`). Salvavidas: VIP (`strategy_vip`).
    /// Gastos fijos: VIP (its recurring expenses) and the Owner (his `fixed_expenses`).
    /// Proyecciones and Escenarios: VIP (`strategy_vip`), paused with `vip_intelligence` (moved from Patrimonio).
    /// Retiro (RT-1): VIP (`strategy_vip`).
    /// Aguinaldo: VIP, and only where mail is read (`readsMail`): the Owner's alone during the launch.
    public var minimum: PlanTier {
        switch self {
        case .debts, .incomeBase: .free
        case .strategy, .distribution: .basic
        case .aguinaldo, .salvavidas, .fixedExpenses, .retirement, .projections, .scenarios: .vip
        }
    }

    /// The operational switch that pauses the row's backend route. The aguinaldo is paused with
    /// `vip_intelligence` (core/feature_flags.py), not with `gmail_automation`.
    public var killSwitch: OpsFlag? {
        switch self {
        case .aguinaldo, .salvavidas, .projections, .scenarios: .vipIntelligence
        case .strategy, .debts, .incomeBase, .fixedExpenses, .retirement, .distribution: nil
        }
    }

    /// The row is computed from mail DINCR reads (CCSS payroll notices): shown only with mail reading.
    public var readsMail: Bool { self == .aguinaldo }

    public enum Availability: Equatable, Sendable {
        /// Not shown at all (an Owner-only row for anyone else).
        case hidden
        case available
        /// Not in the plan: shown locked ("Disponible desde …"), opening the plans screen.
        case locked(PlanTier)
        case paused(OpsFlag)
    }

    /// `canReadMail` is `Profile.canReadMail`; it defaults to false so a caller that forgets it hides
    /// the mail rows rather than offering them.
    public func availability(tier: PlanTier, flags: FeatureFlags, canReadMail: Bool = false) -> Availability {
        if readsMail && !canReadMail { return .hidden }
        guard tier.rank >= minimum.rank else { return .locked(minimum) }
        if let killSwitch, !flags.isEnabled(killSwitch) { return .paused(killSwitch) }
        return .available
    }
}
