package com.dincr.data

import java.net.URI
import java.net.URLDecoder
import java.net.URLEncoder
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.Base64
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.io.IOException

@Serializable
data class AuthSession(
    val accessToken: String,
    val refreshToken: String,
    /** Epoch seconds. */
    val expiresAt: Long,
    val userId: String,
) {
    /** Refresh a minute early so a request never leaves with an expiring token. */
    fun isExpired(nowSeconds: Long = System.currentTimeMillis() / 1000) = nowSeconds + 60 >= expiresAt
}

enum class OAuthProvider(val wire: String) { GOOGLE("google"), APPLE("apple") }

sealed class AuthException(message: String) : Exception(message) {
    class InvalidCallback : AuthException("invalid callback")
    class ProviderRejected : AuthException("provider rejected")
    class SessionRejected : AuthException("session rejected")
    class Network : AuthException("network")
    class SignedOut : AuthException("signed out")
}

/** PKCE pair; only the challenge leaves the device (RFC 7636, S256). */
data class Pkce(val verifier: String) {
    val challenge: String = base64Url(MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray(Charsets.US_ASCII)))

    companion object {
        fun generate(): Pkce = Pkce(base64Url(ByteArray(32).also { SecureRandom().nextBytes(it) }))
        private fun base64Url(bytes: ByteArray) = Base64.getUrlEncoder().withoutPadding().encodeToString(bytes)
    }
}

/** Minimal Supabase GoTrue client: authorize URL, PKCE exchange, refresh, sign-out. */
class SupabaseAuthClient(
    private val projectUrl: String,
    private val anonKey: String,
    private val transport: HttpTransport = OkHttpTransport(),
) {
    private val json = Json { ignoreUnknownKeys = true }
    private val base get() = projectUrl.trimEnd('/')

    fun authorizeUrl(provider: OAuthProvider, redirectTo: String, pkce: Pkce): String {
        val params = buildList {
            add("provider" to provider.wire)
            add("redirect_to" to redirectTo)
            add("code_challenge" to pkce.challenge)
            add("code_challenge_method" to "s256")
            if (provider == OAuthProvider.GOOGLE) add("prompt" to "select_account") else add("scopes" to "name email")
        }
        return "$base/auth/v1/authorize?" + params.joinToString("&") { (k, v) -> "$k=${URLEncoder.encode(v, "UTF-8")}" }
    }

    suspend fun exchange(code: String, verifier: String): AuthSession =
        token("pkce", buildJsonObject { put("auth_code", code); put("code_verifier", verifier) }.toString())

    suspend fun refresh(refreshToken: String): AuthSession =
        token("refresh_token", buildJsonObject { put("refresh_token", refreshToken) }.toString())

    suspend fun signOut(accessToken: String) {
        runCatching {
            transport.send(HttpRequest("POST", "$base/auth/v1/logout?scope=local", mapOf("apikey" to anonKey, "Authorization" to "Bearer $accessToken"), ""))
        }
    }

    @Serializable
    private data class Payload(
        @SerialName("access_token") val accessToken: String,
        @SerialName("refresh_token") val refreshToken: String,
        @SerialName("expires_in") val expiresIn: Long? = null,
        @SerialName("expires_at") val expiresAt: Long? = null,
        val user: User,
    ) {
        @Serializable data class User(val id: String)
    }

    private suspend fun token(grant: String, body: String): AuthSession {
        val response = try {
            transport.send(HttpRequest("POST", "$base/auth/v1/token?grant_type=$grant", mapOf("Content-Type" to "application/json", "apikey" to anonKey), body))
        } catch (error: IOException) {
            throw AuthException.Network()
        }
        if (response.status >= 500) throw AuthException.Network()
        if (response.status !in 200..299) throw AuthException.SessionRejected()
        val payload = runCatching { json.decodeFromString<Payload>(response.body) }.getOrElse { throw AuthException.SessionRejected() }
        val expiry = payload.expiresAt ?: (System.currentTimeMillis() / 1000 + (payload.expiresIn ?: 3600))
        return AuthSession(payload.accessToken, payload.refreshToken, expiry, payload.user.id)
    }

    companion object {
        /**
         * Extracts the authorization code. Fails closed, same rules as iOS: the URL must be
         * exactly our redirect (scheme, host and path; no user, port or fragment) carrying one
         * non-empty `code`. Look-alike URLs, tokens in a fragment, duplicated codes and provider
         * errors are rejected.
         */
        fun authorizationCode(callback: String, redirect: String): String {
            val actual = runCatching { URI(callback) }.getOrNull() ?: throw AuthException.InvalidCallback()
            val expected = URI(redirect)
            val matches = actual.scheme.equals(expected.scheme, ignoreCase = true) &&
                actual.host.equals(expected.host, ignoreCase = true) &&
                actual.rawPath == expected.rawPath && actual.rawUserInfo == null && actual.port == -1 &&
                actual.rawFragment.isNullOrEmpty()
            if (!matches) throw AuthException.InvalidCallback()
            val params = actual.rawQuery.orEmpty().split("&").filter { it.isNotEmpty() }.map { part ->
                val pieces = part.split("=", limit = 2)
                URLDecoder.decode(pieces[0], "UTF-8") to URLDecoder.decode(pieces.getOrElse(1) { "" }, "UTF-8")
            }
            if (params.any { it.first == "error" || it.first == "error_description" }) throw AuthException.ProviderRejected()
            val codes = params.filter { it.first == "code" }
            return codes.singleOrNull()?.second?.takeIf { it.isNotEmpty() } ?: throw AuthException.InvalidCallback()
        }
    }
}

interface SessionStore {
    fun load(): AuthSession?
    fun save(session: AuthSession)
    fun clear()
}

class InMemorySessionStore(private var session: AuthSession? = null) : SessionStore {
    @Synchronized override fun load() = session
    @Synchronized override fun save(session: AuthSession) { this.session = session }
    @Synchronized override fun clear() { session = null }
}

/** Owns the session: refreshes once at a time, signs out when the refresh token is rejected. */
class SessionManager(
    private val auth: SupabaseAuthClient?,
    private val store: SessionStore,
    private val onSignedOut: () -> Unit = {},
) : AccessTokenProvider {
    private val mutex = Mutex()
    private var inFlight: CompletableDeferred<AuthSession>? = null

    val hasSession: Boolean get() = store.load() != null

    fun accept(session: AuthSession) = store.save(session)

    override suspend fun accessToken(forceRefresh: Boolean): String {
        val session = store.load() ?: throw AuthException.SignedOut()
        if (!forceRefresh && !session.isExpired()) return session.accessToken
        return refreshed(session).accessToken
    }

    suspend fun signOut() {
        store.load()?.let { auth?.signOut(it.accessToken) }
        store.clear()
    }

    private suspend fun refreshed(session: AuthSession): AuthSession {
        val (deferred, owner) = mutex.withLock {
            inFlight?.let { it to false } ?: CompletableDeferred<AuthSession>().also { inFlight = it }.let { it to true }
        }
        if (!owner) return deferred.await()
        val client = auth ?: return session.also { finish(deferred, Result.success(it)) }
        val result = runCatching { client.refresh(session.refreshToken) }
        result.onSuccess { store.save(it) }
        result.onFailure { if (it !is AuthException.Network) { store.clear(); onSignedOut() } }
        finish(deferred, result)
        return result.getOrElse { error ->
            throw if (error is AuthException.Network) ApiError.offline(AppLanguage.current()) else AuthException.SignedOut()
        }
    }

    private suspend fun finish(deferred: CompletableDeferred<AuthSession>, result: Result<AuthSession>) {
        mutex.withLock { inFlight = null }
        result.fold({ deferred.complete(it) }, { deferred.completeExceptionally(if (it is AuthException.Network) ApiError.offline(AppLanguage.current()) else AuthException.SignedOut()) })
    }
}
