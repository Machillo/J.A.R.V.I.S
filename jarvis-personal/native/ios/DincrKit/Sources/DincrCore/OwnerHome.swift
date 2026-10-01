import Foundation

/// The Owner's "Hoy" (presentation only). It answers, in this order: how am I today, what needs my
/// attention, what comes next, and how to reach JARVIS. Every figure and item comes from the backend
/// (`/user-product/vip/command-center` or `/basic/dashboard`, and the JARVIS agenda); nothing here
/// computes money. Android twin: none yet (iOS-first Owner redesign).
public enum OwnerHome {
    /// The part of the day the greeting names (device clock).
    public enum Greeting: String, Sendable, Equatable {
        case morning, afternoon, evening
    }

    /// 05:00–11:59 morning, 12:00–18:59 afternoon, otherwise evening.
    public static func greeting(at date: Date, calendar: Calendar = .current) -> Greeting {
        switch calendar.component(.hour, from: date) {
        case 5..<12: .morning
        case 12..<19: .afternoon
        default: .evening
        }
    }

    /// One thing that needs the Owner's attention, in the backend's words.
    public struct Attention: Sendable, Equatable, Identifiable {
        public enum Kind: String, Sendable, Equatable {
            /// Bank notices waiting for Confirm / Correct / Dismiss (Email Monitor).
            case mailReview
            /// A high-severity alert of the command center.
            case urgentAlert
            /// Any other alert of the command center.
            case alert
        }

        public let id: String
        public let kind: Kind
        /// The alert's title; empty for `mailReview`, whose wording is the app's.
        public let title: String
        public let detail: String?
        /// For `mailReview`: how many notices wait.
        public let count: Int?
    }

    /// Pending mail notices first, then urgent alerts, then the rest, each in the backend's order.
    /// Alerts without a title are left out (nothing is shown that the backend did not say).
    public static func attention(from center: CommandCenter?) -> [Attention] {
        guard let center else { return [] }
        var items: [Attention] = []
        if let review = center.automation?.review, review > 0 {
            items.append(Attention(id: "mail", kind: .mailReview, title: "", detail: nil, count: review))
        }
        let alerts = (center.alerts ?? []).enumerated().compactMap { index, alert -> Attention? in
            guard let title = alert.title?.trimmingCharacters(in: .whitespacesAndNewlines), !title.isEmpty else { return nil }
            let detail = [alert.context, alert.action].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " ")
            return Attention(id: "alert.\(index)", kind: alert.severity == "high" ? .urgentAlert : .alert,
                             title: title, detail: detail.isEmpty ? nil : detail, count: nil)
        }
        items += alerts.filter { $0.kind == .urgentAlert } + alerts.filter { $0.kind == .alert }
        return items
    }

    /// The next events of the agenda, in the backend's chronological order.
    public static func upcoming(_ events: [JarvisEvent], limit: Int = 3) -> [JarvisEvent] {
        Array(events.prefix(max(0, limit)))
    }
}

/// What the JARVIS chat offers to start a conversation. The chat's scope is deliberately small:
/// overtime (OT), VGH, holidays and bonuses (payroll records) and the agenda. Nothing here is a
/// general financial assistant, and no action sends anything by itself: a message action only puts
/// a starting phrase in the composer for the Owner to complete and send, and every write still
/// waits for Confirmar.
public enum JarvisQuickAction: String, CaseIterable, Sendable, Identifiable {
    case overtime, bonus, schedule, agenda

    public var id: String { rawValue }

    /// The phrase placed in the composer. JARVIS's engine understands Spanish, so the phrase is
    /// Spanish in both languages (the button title is localized by the app). Nil when the action
    /// navigates instead of writing.
    public var composerText: String? {
        switch self {
        case .overtime: "Hoy hice "
        case .bonus: "Recibí un bono de "
        case .schedule: "Agendá "
        case .agenda: nil
        }
    }

    /// "Ver mi agenda" opens the agenda; it never talks to the chat.
    public var opensAgenda: Bool { self == .agenda }
}
