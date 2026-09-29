package com.dincr.data

import java.net.URI
import java.net.URLDecoder

/**
 * A mail connection coming back from the system browser (`<scheme>://gmail/callback?...`), same
 * contract as `frontend/src/lib/mailOAuth.js`. The backend finished the provider exchange and
 * parked the mailbox; `POST /user-product/vip/mail/oauth/complete {flow, completion}` attaches it
 * to the account, and only the session that started the flow can do so.
 */
data class MailReturn(
    val provider: Provider,
    val status: String,
    val flow: String?,
    val completion: String?,
    /** Per-delivery nonce: the same browser return is handled once. */
    val ret: String?,
) {
    enum class Provider(val param: String) { GMAIL("gmail"), MICROSOFT("microsoft") }

    val isAuthorized: Boolean get() = status == "authorized" && !flow.isNullOrEmpty() && !completion.isNullOrEmpty()

    /** Stable key for the handled ledger. */
    val key: String get() = "${provider.param}:$status:${flow.orEmpty()}:${ret.orEmpty()}"

    companion object {
        /**
         * Parses a return URL. Fails closed (null) unless it is exactly `<scheme>://gmail/callback`
         * for one of [schemes], with no user, port or fragment, and exactly one provider status.
         */
        fun parse(url: String, schemes: Set<String>): MailReturn? {
            val uri = runCatching { URI(url) }.getOrNull() ?: return null
            val scheme = uri.scheme?.lowercase() ?: return null
            if (schemes.none { it.lowercase() == scheme }) return null
            if (!uri.host.equals("gmail", ignoreCase = true) || uri.rawPath != "/callback") return null
            if (uri.rawUserInfo != null || uri.port != -1 || !uri.rawFragment.isNullOrEmpty()) return null
            val params = uri.rawQuery.orEmpty().split("&").filter { it.isNotEmpty() }.map { part ->
                val pieces = part.split("=", limit = 2)
                URLDecoder.decode(pieces[0], "UTF-8") to URLDecoder.decode(pieces.getOrElse(1) { "" }, "UTF-8")
            }
            fun single(name: String): String? = params.filter { it.first == name }.let { if (it.size == 1) it[0].second else null }
            fun count(name: String) = params.count { it.first == name }
            if (listOf("gmail", "microsoft", "flow", "completion", "ret").any { count(it) > 1 }) return null
            val gmail = single("gmail")
            val microsoft = single("microsoft")
            val (provider, status) = when {
                gmail != null && microsoft == null -> Provider.GMAIL to gmail
                microsoft != null && gmail == null -> Provider.MICROSOFT to microsoft
                else -> return null
            }
            if (status.isBlank() || status.length > 64) return null
            return MailReturn(provider, status, single("flow")?.takeIf { it.isNotEmpty() }, single("completion")?.takeIf { it.isNotEmpty() }, single("ret"))
        }

        /** Copy for a provider status that is not a success. */
        fun message(status: String, language: AppLanguage): String = when (status) {
            "denied" -> language.pick("Cancelaste el permiso. Tu correo no se conectó.", "You declined the permission. Your mail was not connected.")
            "invalid_state", "already_processed" -> language.pick("Ese enlace de conexión ya no es válido. Intentá conectar de nuevo.", "That connection link is no longer valid. Try connecting again.")
            "vip_required" -> language.pick("Conectar tu correo es parte de VIP.", "Connecting your mail is part of VIP.")
            "permission_missing" -> language.pick("Falta el permiso de solo lectura. Volvé a conectar y aceptá el permiso.", "The read-only permission is missing. Connect again and accept it.")
            "mailbox_missing", "mailbox_unavailable" -> language.pick("No pudimos usar ese buzón. Probá con otra cuenta.", "We couldn’t use that mailbox. Try another account.")
            else -> language.pick("No pudimos conectar tu correo. Intentá de nuevo.", "We couldn’t connect your mail. Please try again.")
        }
    }
}

/**
 * Remembers handled returns (last [capacity]) so a return delivered twice (cold start and a new
 * intent, a recreated activity) is redeemed once. Persistence is the app's (it passes the keys).
 */
class HandledReturns(initial: List<String> = emptyList(), private val capacity: Int = 50) {
    private val keys = ArrayDeque(initial.takeLast(capacity))

    val snapshot: List<String> get() = keys.toList()

    fun contains(key: String) = key in keys

    fun add(key: String) {
        if (key in keys) return
        keys.addLast(key)
        while (keys.size > capacity) keys.removeFirst()
    }
}
