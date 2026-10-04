import Foundation

/// What a message on screen means (DESIGN.md → Messages). Each kind looks different, so the user
/// recognises it before reading: a technical problem in DINCR never looks like a financial
/// situation, and a financial situation never looks like a failure of the app.
/// Android has the same mapping in `com.dincr.data.MessageKind`.
public enum MessageKind: String, Sendable, CaseIterable {
    /// Something in DINCR failed or is degraded: network, service, a connection that must be redone.
    case technicalError
    /// A financial situation worth the user's attention.
    case attention
    /// Something DINCR found that could help: a recommendation.
    case opportunity
    /// Progress, an improvement or a reached milestone.
    case positive

    /// The kind of a financial alert from the severity the backend sends to the alert screens
    /// (`critical`, `high`, `medium`, `success`). Only `success` is progress; every other severity,
    /// including unknown or missing ones, stays visible as `attention`: a problem is never
    /// downplayed to a suggestion, and a financial alert is never a technical error. No backend
    /// severity means "opportunity" today; recommendations get that kind explicitly.
    public static func financial(severity: String?) -> MessageKind {
        severity?.lowercased() == "success" ? .positive : .attention
    }
}
