package com.dincr.data

import java.util.Locale
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/** The two languages DINCR ships. Spanish (Costa Rica, voseo) is primary. */
enum class AppLanguage(val tag: String) {
    SPANISH("es"), ENGLISH("en");

    fun pick(spanish: String, english: String) = if (this == SPANISH) spanish else english

    companion object {
        fun current(): AppLanguage = if (Locale.getDefault().language == "es") SPANISH else ENGLISH
    }
}

/**
 * A failed DINCR API call with a message safe to show. Mirrors `frontend/src/lib/apiErrors.js`
 * and the iOS `APIError`: Spanish backend `detail` is shown only to Spanish sessions.
 */
class ApiError(
    val kind: Kind,
    val status: Int = 0,
    val code: String = "",
    override val message: String,
    val requestId: String? = null,
    /** For [Kind.FEATURE_UNAVAILABLE]: the paused flag (`financial_writes`, `gmail_automation`…). */
    val feature: String? = null,
) : Exception(message) {
    enum class Kind { OFFLINE, TIMEOUT, SESSION_EXPIRED, SUBSCRIPTION_REQUIRED, FORBIDDEN, NOT_FOUND, VALIDATION, CLIENT, SERVER, DECODING, FEATURE_UNAVAILABLE }

    val isTransient: Boolean get() = kind == Kind.OFFLINE || kind == Kind.TIMEOUT || kind == Kind.SERVER

    companion object {
        fun from(status: Int, body: String, language: AppLanguage, requestId: String?): ApiError {
            var detail = ""
            var code = ""
            var feature: String? = null
            runCatching {
                val root = Json.parseToJsonElement(body).jsonObject
                // Kill switches answer 503 {detail, code: "feature_temporarily_unavailable", feature}.
                root["code"]?.jsonPrimitive?.contentOrNull?.let { code = it }
                feature = root["feature"]?.jsonPrimitive?.contentOrNull
                when (val raw = root["detail"] ?: root["error"]) {
                    is JsonPrimitive -> detail = raw.contentOrNull.orEmpty()
                    is JsonObject -> {
                        detail = raw["message"]?.jsonPrimitive?.contentOrNull.orEmpty()
                        code = raw["code"]?.jsonPrimitive?.contentOrNull.orEmpty()
                    }
                    else -> Unit
                }
            }
            val shown = if (language == AppLanguage.SPANISH) detail else ""
            val t = language::pick
            if (status == 503 && code == FEATURE_UNAVAILABLE_CODE) {
                // The backend message is always Spanish; English sessions get fixed copy.
                return ApiError(Kind.FEATURE_UNAVAILABLE, status, code,
                    shown.ifEmpty { t("Esta función está en mantenimiento. Intentá más tarde.", "This feature is under maintenance. Please try later.") },
                    requestId, feature)
            }
            val (kind, message) = when (status) {
                401 -> Kind.SESSION_EXPIRED to t("Tu sesión venció. Iniciá sesión nuevamente.", "Your session expired. Please sign in again.")
                402 -> Kind.SUBSCRIPTION_REQUIRED to t("Esta función necesita una suscripción activa.", "This feature needs an active subscription.")
                403 -> Kind.FORBIDDEN to shown.ifEmpty { t("No tenés permiso para realizar esta acción.", "You don’t have permission to do this.") }
                404 -> Kind.NOT_FOUND to shown.ifEmpty { t("No encontramos la información solicitada.", "We couldn’t find what you asked for.") }
                409, 422 -> Kind.VALIDATION to shown.ifEmpty { t("Revisá la información e intentá nuevamente.", "Check the information and try again.") }
                in 400..499 -> Kind.CLIENT to shown.ifEmpty { t("No pudimos procesar la solicitud.", "We couldn’t process the request.") }
                else -> Kind.SERVER to t("DINCR no pudo completar la operación. Intentá de nuevo en unos segundos.", "DINCR couldn’t complete the operation. Try again in a few seconds.")
            }
            val finalMessage = if (code == "account_deletion_pending" && detail.isNotEmpty()) detail else message
            return ApiError(kind, status, code, finalMessage, requestId)
        }

        const val FEATURE_UNAVAILABLE_CODE = "feature_temporarily_unavailable"
        /** The server's legal gate (`auth/legal.py`): the current terms are not accepted yet. */
        const val LEGAL_ACCEPTANCE_REQUIRED_CODE = "legal_acceptance_required"

        fun offline(language: AppLanguage) = ApiError(Kind.OFFLINE, message = language.pick("Sin conexión. Revisá tu internet e intentá de nuevo.", "You’re offline. Check your connection and try again."))
        fun timeout(language: AppLanguage) = ApiError(Kind.TIMEOUT, message = language.pick("La solicitud tardó demasiado. Volvé a intentarlo.", "The request took too long. Please try again."))
        fun decoding(language: AppLanguage) = ApiError(Kind.DECODING, message = language.pick("Recibimos una respuesta inesperada. Intentá de nuevo.", "We received an unexpected response. Please try again."))
    }
}
