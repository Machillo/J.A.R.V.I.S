import Foundation

/// "Para atender" (UX-5): the financial matters Hoy surfaces, and the full list behind "Ver todas".
/// Presentation only: it normalizes what the backend already says, orders it and removes
/// duplicates; it never computes money or decides a new priority. Sources:
/// - the VIP command center's `alerts` (state of the month; unknown inputs no longer raise its
///   alerts, #324) and its `automation.review` count (bank notices waiting in the Email Monitor);
/// - the proactive advisor's `alerts` (changes since the previous observation), full list only.
/// Android: `com.dincr.data.AttentionList`.
public struct AttentionItem: Sendable, Equatable, Identifiable {
    /// Order among sources with the same severity (D-3): command center, advisor, then mail.
    public enum Source: Int, Sendable, Equatable, Comparable {
        case commandCenter = 0, advisor = 1, review = 2
        public static func < (lhs: Source, rhs: Source) -> Bool { lhs.rawValue < rhs.rawValue }
    }

    /// Screens an item can open. Only destinations that exist on both platforms; an item without
    /// one is shown without a link (no route is invented from free text).
    public enum Destination: String, Sendable, Equatable, CaseIterable {
        case review, debts, salvavidas, incomeBase, strategy, movements, monthlyReview
    }

    public let id: String
    public let source: Source
    public let severity: String?
    public let kind: MessageKind
    public let title: String
    public let message: String
    /// Advisor items describe a change since the previous observation, not the absolute state.
    public let isChange: Bool
    public let destination: Destination?
}

public enum AttentionList {
    /// Hoy shows at most this many; "Ver todas" opens the rest.
    public static let todayLimit = 3

    /// What Hoy shows: the first items and whether "Ver todas" is needed.
    public struct Today: Sendable, Equatable {
        public let visible: [AttentionItem]
        public let showsSeeAll: Bool
        /// Nothing to show: the section is left out (never an empty or "all clear" block).
        public var isEmpty: Bool { visible.isEmpty }
    }

    /// Hoy (D-3): the command center and its mail-review count, never the advisor.
    public static func today(center: CommandCenter?, mailReviewAvailable: Bool = true, language: AppLanguage = .current) -> Today {
        let all = items(center: center, advisor: nil, mailReviewAvailable: mailReviewAvailable, language: language)
        return Today(visible: Array(all.prefix(todayLimit)), showsSeeAll: all.count > todayLimit)
    }

    /// Presentation order: critical, high, medium, success. A severity the app doesn't know sits
    /// with medium (never downplayed below it, never above a known one).
    public static func rank(_ severity: String?) -> Int {
        switch severity?.lowercased() {
        case "critical": 0
        case "high": 1
        case "success": 3
        default: 2
        }
    }

    /// The advisor's structured routes that have a screen on both platforms. Any other route (or
    /// none) gives no link.
    public static func destination(advisorRoute route: String?) -> AttentionItem.Destination? {
        switch route?.trimmingCharacters(in: CharacterSet(charactersIn: "/ ")).lowercased() {
        case "debts": .debts
        case "vip-emergency": .salvavidas
        // The declared situation lives in Plan → Ingresos y base (UX-7).
        case "situation": .incomeBase
        case "strategy": .strategy
        case "finance", "movements": .movements
        case "vip-monthly-review": .monthlyReview
        default: nil
        }
    }

    /// Advisor codes left out of "Para atender": the health score is not shown as a fact until it has
    /// one canonical calculation (K-2); the alert stays in DINCR → Hoy.
    public static let excludedAdvisorCodes: Set<String> = ["health_score_drop"]

    /// The command center's own "Movimientos por revisar" alert, in either language: the same pending
    /// notices as `automation.review`, so the two become one item.
    static let reviewAlertTitles: Set<String> = ["movimientos por revisar", "transactions to review"]

    /// A source the account can't read right now (a paused kill switch, or a feature its plan
    /// doesn't include): "not available", neither a technical problem nor "nothing pending".
    public static func isUnavailable(_ error: Error) -> Bool {
        guard let error = error as? APIError else { return false }
        return [.featureUnavailable, .forbidden, .subscriptionRequired].contains(error.kind)
    }

    /// Every item, ordered: by severity rank, then source, then the backend's own order.
    /// `mailReviewAvailable` is false while the mail automation is paused: the pending notices are
    /// still a fact, but there is no review screen to open.
    public static func items(center: CommandCenter?, advisor: ProactiveAdvisor?, mailReviewAvailable: Bool = true,
                             language: AppLanguage = .current) -> [AttentionItem] {
        var ranked: [(item: AttentionItem, order: Int)] = []
        let pending = center?.automation?.review ?? 0
        let reviewDestination: AttentionItem.Destination? = mailReviewAvailable ? .review : nil
        var reviewMerged = false

        for (index, alert) in (center?.alerts ?? []).enumerated() {
            guard let title = text(alert.title) else { continue }
            let message = [text(alert.context), text(alert.action)].compactMap { $0 }.joined(separator: " ")
            if pending > 0, reviewAlertTitles.contains(title.lowercased()), !reviewMerged {
                // One item for the pending notices: the command center's words, the Email Monitor link.
                reviewMerged = true
                ranked.append((AttentionItem(id: "review", source: .review, severity: alert.severity, kind: .financial(severity: alert.severity),
                                             title: title, message: message, isChange: false, destination: reviewDestination), index))
                continue
            }
            ranked.append((AttentionItem(id: "center.\(index)", source: .commandCenter, severity: alert.severity,
                                         kind: .financial(severity: alert.severity), title: title, message: message,
                                         isChange: false, destination: nil), index))
        }
        if pending > 0, !reviewMerged {
            ranked.append((AttentionItem(id: "review", source: .review, severity: "medium", kind: .attention,
                                         title: language.pick("Movimientos por revisar", "Transactions to review"),
                                         message: pending == 1 ? language.pick("Hay 1 aviso del correo sin confirmar.", "There is 1 mail notice to confirm.")
                                                               : language.pick("Hay \(pending) avisos del correo sin confirmar.", "There are \(pending) mail notices to confirm."),
                                         isChange: false, destination: reviewDestination), 0))
        }
        for (index, alert) in (advisor?.alerts ?? []).enumerated() {
            guard let title = text(alert.title), !excludedAdvisorCodes.contains(alert.code ?? "") else { continue }
            // A readjusted strategy is a recommendation, not a problem.
            let kind: MessageKind = alert.code == "strategy_changed" ? .opportunity : .financial(severity: alert.severity)
            ranked.append((AttentionItem(id: "advisor.\(alert.id ?? String(index))", source: .advisor, severity: alert.severity, kind: kind,
                                         title: title, message: text(alert.explanation) ?? "", isChange: true,
                                         destination: destination(advisorRoute: alert.action?.route)), index))
        }
        return ranked.sorted { lhs, rhs in
            let left = (rank(lhs.item.severity), lhs.item.source.rawValue, lhs.order)
            let right = (rank(rhs.item.severity), rhs.item.source.rawValue, rhs.order)
            return left < right
        }.map(\.item)
    }

    private static func text(_ value: String?) -> String? {
        guard let value = value?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty else { return nil }
        return value
    }
}
