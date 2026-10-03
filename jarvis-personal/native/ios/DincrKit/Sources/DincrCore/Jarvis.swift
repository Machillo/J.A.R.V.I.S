import Foundation

/// JARVIS: the Owner's personal capabilities inside DINCR (JARVIS recovery roadmap, step J0).
///
/// DINCR has four kinds of account: Free, Basic and VIP (plans) and the single Owner (a server role,
/// never a plan). The Owner uses the public app at VIP level (#296) and, on top of it, JARVIS.
/// - Only the role in `/auth/me` opens it: never a plan code, a stored flag or a local copy of the
///   profile. The app only shows or hides the entry; the backend decides every JARVIS request.
/// - Admin is not the Owner and never gets JARVIS.
///
/// Android twin: `Jarvis.kt`.
public enum Jarvis {
    /// Whether the app offers JARVIS to this identity.
    public static func isAvailable(to profile: Profile?) -> Bool { profile?.isOwner == true }

    /// The personal capabilities JARVIS brings back, in the recovery roadmap's order. A section not
    /// ported yet opens a "being restored" screen; the step that ports it makes it available here,
    /// with its own tests.
    public enum Section: String, CaseIterable, Sendable, Identifiable, Hashable {
        case chat, memory, calendar, strategy, money
        case moneyControl = "money_control"
        case wealth, records
        /// "Análisis financiero": the historical web Finanzas tab (spending, flow, net worth, engine).
        case analysis

        public var id: String { rawValue }

        /// Ported to the native app: the chat (J1), the agenda (J2), the financial analysis and money
        /// control (its cuentas por cobrar); the others still open "being restored".
        public var isAvailable: Bool { [.chat, .calendar, .analysis, .moneyControl].contains(self) }
    }
}
