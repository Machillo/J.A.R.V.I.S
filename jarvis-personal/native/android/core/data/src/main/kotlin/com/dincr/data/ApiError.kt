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
) : Exception(message) {
    enum class Kind { OFFLINE, TIMEOUT, SESSION_EXPIRED, SUBSCRIPTION_REQUIRED, FORBIDDEN, NOT_FOUND, VALIDATION, CLIENT, SERVER, DECODING }

    val isTransient: Boolean get() = kind == Kind.OFFLINE || kind == Kind.TIMEOUT || kind == Kind.SERVER

    companion object {
        fun from(status: Int, body: String, language: AppLanguage, requestId: String?): ApiError {
            var detail = ""
            var code = ""
            runCatching {
                val root = Json.parseToJsonElement(body).jsonObject
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

        fun offline(language: AppLanguage) = ApiError(Kind.OFFLINE, message = language.pick("Sin conexión. Revisá tu internet e intentá de nuevo.", "You’re offline. Check your connection and try again."))
        fun timeout(language: AppLanguage) = ApiError(Kind.TIMEOUT, message = language.pick("La solicitud tardó demasiado. Volvé a intentarlo.", "The request took too long. Please try again."))
        fun decoding(language: AppLanguage) = ApiError(Kind.DECODING, message = language.pick("Recibimos una respuesta inesperada. Intentá de nuevo.", "We received an unexpected response. Please try again."))
    }
}
