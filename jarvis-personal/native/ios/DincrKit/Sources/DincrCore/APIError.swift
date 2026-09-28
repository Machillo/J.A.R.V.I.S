import Foundation

/// A failed DINCR API call, with a message safe to show the user.
///
/// Mirrors `frontend/src/lib/apiErrors.js`: backend `detail` messages are written in Spanish,
/// so they are shown only to Spanish sessions; everyone else gets the status message.
public struct APIError: Error, Sendable, Equatable {
    public enum Kind: Sendable, Equatable {
        case offline
        case timeout
        case sessionExpired
        case subscriptionRequired
        case forbidden
        case notFound
        case validation
        case client
        case server
        case decoding
    }

    public let kind: Kind
    public let status: Int
    public let code: String
    public let message: String
    public let requestID: String?

    public init(kind: Kind, status: Int = 0, code: String = "", message: String, requestID: String? = nil) {
        self.kind = kind; self.status = status; self.code = code; self.message = message; self.requestID = requestID
    }

    /// Whether retrying the same request later may succeed (drives the "Reintentar" affordance).
    public var isTransient: Bool {
        switch kind {
        case .offline, .timeout, .server: true
        default: false
        }
    }

    static func from(status: Int, body: Data, language: AppLanguage, requestID: String?) -> APIError {
        var detail = ""
        var code = ""
        if let object = try? JSONSerialization.jsonObject(with: body) as? [String: Any] {
            let raw = object["detail"] ?? object["error"]
            if let text = raw as? String { detail = text }
            if let nested = raw as? [String: Any] {
                detail = nested["message"] as? String ?? ""
                code = nested["code"] as? String ?? ""
            }
        }
        let shown = language == .spanish ? detail : ""
        let t = language.pick
        let (kind, message): (Kind, String) = switch status {
        case 401: (.sessionExpired, t("Tu sesión venció. Iniciá sesión nuevamente.", "Your session expired. Please sign in again."))
        case 402: (.subscriptionRequired, t("Esta función necesita una suscripción activa.", "This feature needs an active subscription."))
        case 403: (.forbidden, shown.isEmpty ? t("No tenés permiso para realizar esta acción.", "You don’t have permission to do this.") : shown)
        case 404: (.notFound, shown.isEmpty ? t("No encontramos la información solicitada.", "We couldn’t find what you asked for.") : shown)
        case 409, 422: (.validation, shown.isEmpty ? t("Revisá la información e intentá nuevamente.", "Check the information and try again.") : shown)
        case 400..<500: (.client, shown.isEmpty ? t("No pudimos procesar la solicitud.", "We couldn’t process the request.") : shown)
        default: (.server, t("DINCR no pudo completar la operación. Intentá de nuevo en unos segundos.", "DINCR couldn’t complete the operation. Try again in a few seconds."))
        }
        // Account-deletion states carry an explicit message already in the session language.
        let finalMessage = code == "account_deletion_pending" && !detail.isEmpty ? detail : message
        return APIError(kind: kind, status: status, code: code, message: finalMessage, requestID: requestID)
    }

    static func offline(_ language: AppLanguage) -> APIError {
        APIError(kind: .offline, message: language.pick("Sin conexión. Revisá tu internet e intentá de nuevo.", "You’re offline. Check your connection and try again."))
    }

    static func timeout(_ language: AppLanguage) -> APIError {
        APIError(kind: .timeout, message: language.pick("La solicitud tardó demasiado. Volvé a intentarlo.", "The request took too long. Please try again."))
    }

    static func decoding(_ language: AppLanguage) -> APIError {
        APIError(kind: .decoding, message: language.pick("Recibimos una respuesta inesperada. Intentá de nuevo.", "We received an unexpected response. Please try again."))
    }
}

/// The two languages DINCR ships. Spanish (Costa Rica, voseo) is primary.
public enum AppLanguage: String, Sendable {
    case spanish = "es"
    case english = "en"

    public static var current: AppLanguage {
        let preferred = Locale.preferredLanguages.first ?? "es"
        return preferred.hasPrefix("es") ? .spanish : .english
    }

    public func pick(_ spanish: String, _ english: String) -> String {
        self == .spanish ? spanish : english
    }
}
