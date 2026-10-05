import Foundation

/// "Tu plan del mes" (UX-3): Estrategia and Distribución read as one plan. It is a reading of the
/// strategy answer the identity already gets (`StrategySource`: Basic, VIP Users or the Owner), not
/// a new calculation: the amount to plan, how DINCR splits it and a short why are the backend's own
/// figures and text. The only thing decided here is whether the parts exactly make up the amount
/// to plan; only then are they drawn as a whole (a donut). Android: `com.dincr.data.MonthPlan`.
public struct MonthPlan: Sendable, Equatable {
    public enum Kind: String, Sendable, Equatable { case basic, users, owner }

    /// One part of the split, as the backend sent it. `percentage` exists only for the dashboard.
    public struct Part: Sendable, Equatable, Identifiable {
        public let id: String
        public let label: String
        public let amount: Decimal?
        public let percentage: Double?
    }

    public let kind: Kind
    /// The amount DINCR plans with: Basic `strategic_margin`, dashboard `allocation_base_amount`.
    public let base: Decimal?
    public let parts: [Part]
    /// One sentence on what DINCR recommends: Basic recommendation (or director note), dashboard
    /// priority title (or objective).
    public let headline: String?
    /// The commitments exceed the income / there is no real surplus this month.
    public let isCritical: Bool
    /// What a critical answer says: Basic recommendation, dashboard objective (as before UX-3).
    public let criticalDetail: String?
    public let needsIncome: Bool
    /// The income was estimated from recorded movements (Basic answers say so).
    public let usesObservedIncome: Bool

    public init(_ strategy: PlanStrategy, language: AppLanguage = .current) {
        switch strategy {
        case .basic(let basic):
            kind = .basic
            base = basic.strategicMargin
            parts = (basic.allocations ?? []).enumerated().map { index, allocation in
                Part(id: "\(index)-\(allocation.bucket ?? "")", label: allocation.label ?? allocation.bucket ?? "—",
                     amount: allocation.amount, percentage: nil)
            }
            headline = Self.text(basic.recommendation) ?? Self.text(basic.directorNote)
            isCritical = basic.status == "critical"
            criticalDetail = Self.text(basic.recommendation)
            needsIncome = basic.needsIncome
            usesObservedIncome = basic.usesObservedIncome
        case .dashboard(let dashboard):
            let plan = dashboard.strategy
            kind = plan?.isOwnerScope == true ? .owner : .users
            base = plan?.allocationBaseAmount
            parts = (plan?.allocationItems ?? []).enumerated().map { index, item in
                Part(id: "\(index)-\(item.key ?? "")", label: DistributionLabels.bucket(item.key, targetName: item.targetName, language: language),
                     amount: item.amount, percentage: item.percentage)
            }
            headline = Self.text(plan?.priority?.title) ?? Self.text(plan?.objective) ?? Self.text(dashboard.content)
            isCritical = plan?.status == "critical"
            criticalDetail = Self.text(plan?.objective)
            needsIncome = plan?.needsIncome ?? false
            usesObservedIncome = false
        }
    }

    /// The summary's sentence: the headline, unless a critical message already says the same.
    public var summaryHeadline: String? {
        guard let headline else { return nil }
        return isCritical && headline == criticalDetail ? nil : headline
    }

    /// The parts as a composition (no currency of their own: every amount is the profile currency the
    /// strategy answer uses).
    public var composition: Composition {
        Composition(parts.map { CompositionItem(id: $0.id, label: $0.label, value: $0.amount) })
    }

    /// The parts exactly make up the amount to plan, so the whole can be drawn. A part with an
    /// unknown amount, an unknown amount to plan, or parts that leave money unassigned (or add up to
    /// more) are listed instead: DINCR never draws a whole the backend didn't send.
    public var showsComposition: Bool {
        let composition = composition
        guard composition.isDrawable, let base, let total = composition.total else { return false }
        return total == base
    }

    private static func text(_ value: String?) -> String? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else { return nil }
        return value
    }
}
