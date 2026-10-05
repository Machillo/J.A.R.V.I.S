import Foundation

/// The Owner's "Hoy" (presentation only). It answers, in this order: how am I today, what needs my
/// attention (`AttentionList`, the same "Para atender" as VIP), what comes next, and how to reach
/// JARVIS. Every figure and item comes from the backend
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
