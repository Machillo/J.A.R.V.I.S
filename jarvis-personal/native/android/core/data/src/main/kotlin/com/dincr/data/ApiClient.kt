package com.dincr.data

import java.io.IOException
import java.io.InterruptedIOException
import java.util.UUID
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody

/** Supplies the bearer token. `forceRefresh` is used once after a 401. */
fun interface AccessTokenProvider {
    suspend fun accessToken(forceRefresh: Boolean): String
}

/** A plain HTTP exchange, so tests can script responses without a server. */
data class HttpRequest(val method: String, val url: String, val headers: Map<String, String>, val body: String?)
data class HttpResponse(val status: Int, val body: String)

fun interface HttpTransport {
    /** Throws [IOException] on network failure. */
    suspend fun send(request: HttpRequest): HttpResponse
}

class OkHttpTransport(
    private val client: OkHttpClient = OkHttpClient.Builder()
        .callTimeout(20, TimeUnit.SECONDS)
        .build(),
) : HttpTransport {
    override suspend fun send(request: HttpRequest): HttpResponse = withContext(Dispatchers.IO) {
        val body = request.body?.toRequestBody("application/json".toMediaType())
            ?: if (request.method == "GET" || request.method == "HEAD") null else ByteArray(0).toRequestBody(null)
        val okRequest = Request.Builder().url(request.url).method(request.method, body)
            .apply { request.headers.forEach { (name, value) -> header(name, value) } }
            .build()
        client.newCall(okRequest).execute().use { response -> HttpResponse(response.code, response.body?.string().orEmpty()) }
    }
}

/**
 * DINCR API client. Same contract as `frontend/src/lib/authenticatedFetch.js` and iOS `APIClient`:
 * Bearer token, Accept-Language, stable X-Request-ID, X-Retry-Attempt; safe methods retry up to
 * 2 times on 408/425/429/502/503/504 or network loss; writes are never retried and creates carry
 * an `X-Idempotency-Key`; a 401 refreshes the session once.
 */
class ApiClient(
    private val baseUrl: String,
    private val tokens: AccessTokenProvider,
    private val transport: HttpTransport = OkHttpTransport(),
    private val language: AppLanguage = AppLanguage.current(),
    private val backoff: suspend (Int) -> Unit = { attempt -> delay(400L shl attempt) },
) {
    val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }

    suspend inline fun <reified T> get(path: String, query: Map<String, String> = emptyMap()): T =
        decode(perform("GET", path, query, null))

    suspend inline fun <reified B, reified T> send(method: String, path: String, body: B, idempotencyKey: String? = null): T =
        decode(perform(method, path, emptyMap(), json.encodeToString(body), idempotencyKey))

    suspend inline fun <reified T> send(method: String, path: String): T =
        decode(perform(method, path, emptyMap(), null))

    inline fun <reified T> decode(body: String): T =
        try {
            json.decodeFromString<T>(body.ifEmpty { "{}" })
        } catch (error: Exception) {
            throw ApiError.decoding(currentLanguage)
        }

    val currentLanguage: AppLanguage get() = language

    suspend fun perform(method: String, path: String, query: Map<String, String>, body: String?, idempotencyKey: String? = null): String {
        val requestId = UUID.randomUUID().toString()
        val safe = method == "GET" || method == "HEAD"
        val maxRetries = if (safe) 2 else 0
        var attempt = 0
        var refreshed = false
        var token = tokens.accessToken(false)
        val url = baseUrl.trimEnd('/').plus(path).toHttpUrl().newBuilder()
            .apply { query.forEach { (key, value) -> addQueryParameter(key, value) } }
            .build().toString()

        while (true) {
            val headers = buildMap {
                put("Accept", "application/json")
                if (body != null) put("Content-Type", "application/json")
                put("Accept-Language", language.tag)
                put("X-Request-ID", requestId)
                put("X-Retry-Attempt", attempt.toString())
                put("Authorization", "Bearer $token")
                if (idempotencyKey != null) put("X-Idempotency-Key", idempotencyKey)
            }
            val response = try {
                transport.send(HttpRequest(method, url, headers, body))
            } catch (error: IOException) {
                if (attempt < maxRetries) { backoff(attempt); attempt += 1; continue }
                throw if (error is InterruptedIOException) ApiError.timeout(language) else ApiError.offline(language)
            }
            if (response.status == 401 && !refreshed) {
                refreshed = true
                token = tokens.accessToken(true)
                continue
            }
            if (response.status in RETRYABLE_STATUS && attempt < maxRetries) {
                backoff(attempt); attempt += 1; continue
            }
            if (response.status !in 200..299) throw ApiError.from(response.status, response.body, language, requestId)
            return response.body
        }
    }

    companion object {
        val RETRYABLE_STATUS = setOf(408, 425, 429, 502, 503, 504)
    }
}
