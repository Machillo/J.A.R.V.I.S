import Foundation

/// UX-8 — "Recomendación de DINCR": the priority DINCR already recommends and why, read from the
/// strategy answer the identity gets (`PlanStrategy`); no new calculation, rule or score. Basic: the
/// engine's `priority` code (named here) and its own `recommendation`; VIP Users and the Owner: the
/// dashboard priority's title and detail. The engines name one priority and no other option, so none
/// is offered and it can't be changed. Free has no strategy (no card); without a declared income
/// there is nothing to recommend yet. Android: `com.dincr.data.RecommendedPriority`.
public struct RecommendedPriority: Sendable, Equatable {
    public let title: String
    /// Why DINCR recommends it, in the engine's own words; nil when the screen already says it.
    public let why: String?

    public static func of(_ strategy: PlanStrategy, language: AppLanguage = .current) -> RecommendedPriority? {
        switch strategy {
        case .basic(let basic):
            guard !basic.needsIncome, let title = basicTitle(basic.priority, language: language) else { return nil }
            // A critical month already shows the same text as its message.
            return RecommendedPriority(title: title, why: basic.status == "critical" ? nil : text(basic.recommendation))
        case .dashboard(let dashboard):
            guard let plan = dashboard.strategy, !plan.needsIncome, let title = text(plan.priority?.title) else { return nil }
            return RecommendedPriority(title: title, why: text(plan.priority?.detail))
        }
    }

    /// The Basic engine's priority codes (`build_basic_strategy`), named; an unknown code shows nothing.
    static func basicTitle(_ code: String?, language: AppLanguage) -> String? {
        switch code {
        case "debt": language.pick("Pagar deudas", "Pay down debt")
        case "emergency": language.pick("Fondo de emergencia", "Emergency fund")
        case "goals": language.pick("Tus metas", "Your goals")
        case "wealth_building": language.pick("Construir patrimonio", "Build wealth")
        case "complete_profile": language.pick("Completar tus gastos esenciales", "Add your essential expenses")
        case "stabilize": language.pick("Estabilizar tu mes", "Stabilize your month")
        default: nil
        }
    }

    private static func text(_ value: String?) -> String? {
        guard let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty else { return nil }
        return trimmed
    }
}
