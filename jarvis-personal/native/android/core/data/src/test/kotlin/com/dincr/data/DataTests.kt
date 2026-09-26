package com.dincr.data

import java.io.IOException
import java.math.BigDecimal
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

private fun fixture(name: String) = checkNotNull(object {}.javaClass.getResource("/$name.json")).readText()
private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }

/** Same JSON contract and behaviors as the iOS DincrCore tests. */
class ContractTest {
    @Test fun decodesFreeDashboardAndIgnoresUnknownFields() {
        val dashboard = json.decodeFromString<FreeDashboard>(fixture("free_dashboard"))
        assertEquals("2026-09", dashboard.month)
        assertEquals(0, BigDecimal("257549.5").compareTo(dashboard.available))
        assertEquals(2, dashboard.categories.size)
    }

    @Test fun unknownAvailableStaysUnknown() {
        val dashboard = json.decodeFromString<FreeDashboard>("""{"month":"2026-09","income":1,"expenses":1,"categories":[],"monthly_history":[]}""")
        assertNull("unknown must stay unknown, not zero", dashboard.available)
    }

    @Test fun decodesMovements() {
        val rows = json.decodeFromString<List<Movement>>(fixture("free_movements"))
        assertEquals(4, rows.size)
        assertEquals(MovementKind.INCOME, rows[0].kind)
        assertTrue(rows[0].editable)
        assertEquals("cents survive decoding", 0, BigDecimal("18450.5").compareTo(rows[1].amount))
        assertFalse(rows[2].editable)
        assertEquals("debt payments arrive as read-only expenses", MovementKind.EXPENSE, rows[3].kind)
        assertNull(rows[3].day)
        assertNull(rows[3].category)
    }

    @Test fun decodesProfilePreferences() {
        val profile = json.decodeFromString<Profile>(fixture("me"))
        assertEquals("basic", profile.plan)
        assertEquals("Ana", profile.firstName)
        val format = MoneyFormat.from(profile)
        assertEquals("USD", format.currency)
        assertEquals(MoneyFormat.Separators.COMMA_DOT, format.separators)
        assertEquals(MoneyFormat.Placement.AFTER, format.placement)
    }

    @Test fun ownerSessionsAreRecognized() {
        listOf("owner", "admin").forEach { assertTrue(json.decodeFromString<Profile>("""{"id":1,"role":"$it"}""").isOwner) }
    }

    @Test fun encodesBodiesInSnakeCaseWithExactAmounts() {
        val body = Json.encodeToString(EntryCreate.serializer(), EntryCreate(BigDecimal("18450.50"), "Súper", "Comida", "2026-09-25"))
        assertTrue(body, body.contains("\"entry_date\":\"2026-09-25\""))
        assertTrue(body, body.contains("\"amount\":18450.5"))
    }

    @Test fun movementIdKeepsItsColon() {
        assertEquals("expense:42", LiveDincrService.encode("expense:42"))
        assertEquals("a%2Fb", LiveDincrService.encode("a/b"))
    }
}

class MoneyFormatTest {
    @Test fun colones() {
        val f = MoneyFormat()
        assertEquals("₡1.234.567", f.format(BigDecimal(1_234_567)))
        assertEquals("−₡18.450", f.format(BigDecimal(18_450), MoneyFormat.Sign.EXPENSE))
        assertEquals("+₡432.500", f.format(BigDecimal(432_500), MoneyFormat.Sign.INCOME))
        assertEquals("−₡5.000", f.format(BigDecimal(-5_000)))
    }

    @Test fun dollars() {
        assertEquals("1,234.50 $", MoneyFormat("USD", MoneyFormat.Separators.COMMA_DOT, MoneyFormat.Placement.AFTER).format(BigDecimal("1234.5")))
    }

    @Test fun spoken() {
        assertEquals("menos 18450 colones", MoneyFormat().spoken(BigDecimal(18_450), MoneyFormat.Sign.EXPENSE, AppLanguage.SPANISH))
        assertEquals("257550 colones", MoneyFormat().spoken(BigDecimal(257_550), language = AppLanguage.ENGLISH))
        assertEquals("1234.5 dollars", MoneyFormat("USD").spoken(BigDecimal("1234.5"), language = AppLanguage.ENGLISH))
        assertEquals("1 colón", MoneyFormat().spoken(BigDecimal.ONE, language = AppLanguage.SPANISH))
    }

    @Test fun parsesValidInput() {
        assertEquals(0, BigDecimal(18_450).compareTo(AmountInput.parse("18.450", MoneyFormat.Separators.DOT_COMMA)))
        assertEquals(0, BigDecimal("18450.75").compareTo(AmountInput.parse("18.450,75", MoneyFormat.Separators.DOT_COMMA)))
        assertEquals(0, BigDecimal("1234.5").compareTo(AmountInput.parse("1,234.5", MoneyFormat.Separators.COMMA_DOT)))
        assertEquals(0, BigDecimal("1.5").compareTo(AmountInput.parse("1,5", MoneyFormat.Separators.DOT_COMMA)))
    }

    @Test fun rejectsAmbiguousOrInvalidInput() {
        listOf("", "0", "-5", "abc", "1,2,3", "12e3", "1,5", "12,34,567", "1.5.2", "1,234,56").forEach {
            assertNull("\"$it\" must be rejected", AmountInput.parse(it, MoneyFormat.Separators.COMMA_DOT))
        }
    }
}

private class ScriptedTransport(vararg steps: Any) : HttpTransport {
    private val queue = ArrayDeque(steps.toList())
    val requests = mutableListOf<HttpRequest>()
    override suspend fun send(request: HttpRequest): HttpResponse {
        requests += request
        return when (val step = queue.removeFirstOrNull() ?: HttpResponse(500, "{}")) {
            is HttpResponse -> step
            is IOException -> throw step
            else -> error("bad step")
        }
    }
}

private class CountingTokens : AccessTokenProvider {
    var refreshes = 0
    override suspend fun accessToken(forceRefresh: Boolean): String { if (forceRefresh) refreshes += 1; return "token-$refreshes" }
}

class ApiClientTest {
    private fun client(transport: HttpTransport, tokens: AccessTokenProvider = CountingTokens(), language: AppLanguage = AppLanguage.SPANISH) =
        ApiClient("https://api.example.test", tokens, transport, language, backoff = {})

    @Test fun sendsWebClientHeaders() = runTest {
        val transport = ScriptedTransport(HttpResponse(200, "{}"))
        client(transport).perform("GET", "/auth/me", emptyMap(), null)
        val headers = transport.requests.single().headers
        assertEquals("Bearer token-0", headers["Authorization"])
        assertEquals("es", headers["Accept-Language"])
        assertEquals("0", headers["X-Retry-Attempt"])
        assertEquals("https://api.example.test/auth/me", transport.requests.single().url)
    }

    @Test fun retriesSafeRequestsWithStableRequestId() = runTest {
        val transport = ScriptedTransport(HttpResponse(503, "{}"), IOException("lost"), HttpResponse(200, "{}"))
        client(transport).perform("GET", "/x", emptyMap(), null)
        assertEquals(3, transport.requests.size)
        assertEquals(1, transport.requests.map { it.headers["X-Request-ID"] }.toSet().size)
        assertEquals(listOf("0", "1", "2"), transport.requests.map { it.headers["X-Retry-Attempt"] })
    }

    @Test fun neverRetriesWrites() = runTest {
        val transport = ScriptedTransport(HttpResponse(503, "{}"), HttpResponse(200, "{}"))
        try { client(transport).perform("POST", "/x", emptyMap(), "{}"); fail("expected failure") } catch (_: ApiError) {}
        assertEquals("a write must not be sent twice", 1, transport.requests.size)
    }

    @Test fun refreshesOnceOn401() = runTest {
        val tokens = CountingTokens()
        val transport = ScriptedTransport(HttpResponse(401, "{}"), HttpResponse(200, "{}"))
        client(transport, tokens).perform("GET", "/x", emptyMap(), null)
        assertEquals(1, tokens.refreshes)
        assertEquals("Bearer token-1", transport.requests.last().headers["Authorization"])
    }

    @Test fun spanishDetailOnlyForSpanishSessions() = runTest {
        val body = """{"detail":"El periodo debe tener formato YYYY-MM."}"""
        for ((language, expected) in listOf(AppLanguage.SPANISH to "El periodo debe tener formato YYYY-MM.", AppLanguage.ENGLISH to "Check the information and try again.")) {
            try { client(ScriptedTransport(HttpResponse(422, body)), language = language).perform("GET", "/x", emptyMap(), null); fail() }
            catch (error: ApiError) { assertEquals(ApiError.Kind.VALIDATION, error.kind); assertEquals(expected, error.message) }
        }
    }

    @Test fun offlineAfterRetries() = runTest {
        val transport = ScriptedTransport(IOException("a"), IOException("b"), IOException("c"))
        try { client(transport).perform("GET", "/x", emptyMap(), null); fail() }
        catch (error: ApiError) { assertEquals(ApiError.Kind.OFFLINE, error.kind); assertTrue(error.isTransient) }
    }
}

class AuthTest {
    @Test fun pkceMatchesRfc7636Vector() {
        assertEquals("E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM", Pkce("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk").challenge)
    }

    private val redirect = "com.dincr.app.nativedev://auth/callback"

    @Test fun callbackAcceptsOnlyCodeOnTheExactRedirect() {
        assertEquals("abc", SupabaseAuthClient.authorizationCode("$redirect?code=abc", redirect))
        assertEquals("abc", SupabaseAuthClient.authorizationCode("COM.DINCR.APP.NATIVEDEV://auth/callback?code=abc&state=s", redirect))
        try { SupabaseAuthClient.authorizationCode("$redirect?error=access_denied", redirect); fail() } catch (_: AuthException.ProviderRejected) {}
    }

    @Test fun callbackRejectsAnythingElse() {
        listOf(
            "evil://auth/callback?code=abc",
            "com.dincr.app://auth/callback?code=abc",
            "com.dincr.app.nativedev://auth/callbackX?code=abc",
            "com.dincr.app.nativedev://auth/callback/x?code=abc",
            "com.dincr.app.nativedev://evil/callback?code=abc",
            "com.dincr.app.nativedev://user@auth/callback?code=abc",
            "com.dincr.app.nativedev://auth:99/callback?code=abc",
            "com.dincr.app.nativedev://auth/callback#access_token=x&refresh_token=y",
            "com.dincr.app.nativedev://auth/callback?code=abc#access_token=x",
            "com.dincr.app.nativedev://auth/callback",
            "com.dincr.app.nativedev://auth/callback?code=",
            "com.dincr.app.nativedev://auth/callback?code=a&code=b",
            "not a url at all",
        ).forEach {
            try { SupabaseAuthClient.authorizationCode(it, redirect); fail(it) } catch (_: AuthException.InvalidCallback) {}
        }
    }

    @Test fun authorizeUrlCarriesPkce() {
        val pkce = Pkce("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")
        val url = SupabaseAuthClient("https://project.example.test", "anon").authorizeUrl(OAuthProvider.GOOGLE, redirect, pkce)
        assertTrue(url, url.startsWith("https://project.example.test/auth/v1/authorize?provider=google"))
        assertTrue(url, url.contains("code_challenge=${pkce.challenge}") && url.contains("code_challenge_method=s256") && url.contains("prompt=select_account"))
    }

    private fun expired() = AuthSession("old", "r1", 0, "u1")

    @Test fun concurrentCallersShareOneRefresh() = runTest {
        val transport = ScriptedTransport(HttpResponse(200, """{"access_token":"fresh","refresh_token":"r2","expires_in":3600,"user":{"id":"u1"}}"""))
        val store = InMemorySessionStore(expired())
        val manager = SessionManager(SupabaseAuthClient("https://p.example.test", "anon", transport), store)
        val tokens = listOf(async { manager.accessToken(false) }, async { manager.accessToken(false) }).awaitAll()
        assertEquals(listOf("fresh", "fresh"), tokens)
        assertEquals(1, transport.requests.size)
        assertEquals("anon", transport.requests.single().headers["apikey"])
        assertEquals("r2", store.load()?.refreshToken)
    }

    @Test fun rejectedRefreshSignsOut() = runTest {
        var signedOut = false
        val store = InMemorySessionStore(expired())
        val manager = SessionManager(SupabaseAuthClient("https://p.example.test", "anon", ScriptedTransport(HttpResponse(400, "{}"))), store) { signedOut = true }
        try { manager.accessToken(false); fail() } catch (_: AuthException.SignedOut) {}
        assertNull(store.load())
        assertTrue(signedOut)
    }

    @Test fun networkFailureKeepsSession() = runTest {
        val store = InMemorySessionStore(expired())
        val manager = SessionManager(SupabaseAuthClient("https://p.example.test", "anon", ScriptedTransport(IOException("offline"))), store)
        try { manager.accessToken(false); fail() } catch (_: ApiError) {}
        assertTrue("being offline must not sign the user out", store.load() != null)
    }
}
