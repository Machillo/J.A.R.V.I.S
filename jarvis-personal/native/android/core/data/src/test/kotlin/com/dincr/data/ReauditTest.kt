package com.dincr.data

import java.math.BigDecimal
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.async
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.yield
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/**
 * Re-audit of C4 against main after #269/#272 (money limits, currency rows, launch policy,
 * session isolation, redirects). The Swift twin is `ReauditTests` in DincrKit.
 */
class ReauditTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }
    private fun d(value: String) = BigDecimal(value)
    private val dotComma = MoneyFormat.Separators.DOT_COMMA
    private val commaDot = MoneyFormat.Separators.COMMA_DOT

    // --- Money limits: amount is NUMERIC(12,2) for every write of this app. -----------------

    @Test fun amountLimitIsTheColumnOfEveryWrite() {
        assertEquals(0, d("9999999999.99").compareTo(AmountInput.MAX_AMOUNT))
        assertEquals(0, d("9999999999.99").compareTo(AmountInput.parse("9.999.999.999,99", dotComma)))
        assertEquals(0, d("9999999999.99").compareTo(AmountInput.parse("9999999999,99", dotComma)))
        assertEquals(0, d("9999999999.99").compareTo(AmountInput.parse("9,999,999,999.99", commaDot)))
        assertEquals(0, d("0.01").compareTo(AmountInput.parse("0,01", dotComma)))
        for ((text, separators) in listOf(
            "10.000.000.000" to dotComma, "10.000.000.000,00" to dotComma, "10000000000" to dotComma,
            "99.999.999.999,99" to dotComma, "10,000,000,000.00" to commaDot, "999999999999.99" to commaDot,
            "1e30" to dotComma, "1e300" to commaDot, "1E+30" to commaDot, "NaN" to dotComma, "Infinity" to commaDot,
            "-Infinity" to dotComma, "-0,01" to dotComma, "0" to dotComma, "0,00" to dotComma, "0x10" to commaDot,
            "9.999.999.999,991" to dotComma, "1,000" to dotComma, "1.000" to commaDot, "1.5" to dotComma,
            "１２" to dotComma, "٣" to dotComma,
        )) assertNull("\"$text\" must be rejected", AmountInput.parse(text, separators))
    }

    @Test fun displayRoundsHalfUpButEditingKeepsCents() {
        val crc = MoneyFormat("CRC", dotComma)
        assertEquals("₡3", crc.format(d("2.5")))
        assertEquals("₡18.451", crc.format(d("18450.50")))
        assertEquals("18.450,5", crc.inputText(d("18450.50")))
        assertEquals(0, d("18450.5").compareTo(AmountInput.parse(crc.inputText(d("18450.50")), dotComma)))
        assertEquals("9.999.999.999,99", crc.inputText(d("9999999999.99")))
        assertEquals("menos 18451 colones", crc.spoken(d("18450.5"), MoneyFormat.Sign.EXPENSE, AppLanguage.SPANISH))
        assertEquals("$18,450.50", MoneyFormat("USD", commaDot).format(d("18450.5")))
    }

    // --- Untouched edits send the stored amount digit for digit, and never a currency. -------

    @Test fun untouchedAmountRoundTripsExactly() {
        for (stored in listOf("9999999999.99", "0.1", "0.01", "18450.5", "100.10", "1234567.89")) {
            val row = json.decodeFromString<Movement>("""{"movement_id":"expense:1","transaction_date":"2026-09-01","amount":$stored,"transaction_type":"expense","editable":true}""")
            val body = json.encodeToString(MovementUpdate.serializer(), MovementUpdate("2026-09-01", "x", row.amount, "expense", "Otros"))
            val sent = json.parseToJsonElement(body).jsonObject["amount"].toString()
            assertEquals(stored, 0, d(stored).compareTo(d(sent)))
        }
    }

    @Test fun writesNeverCarryACurrencyOrRate() {
        val update = json.parseToJsonElement(json.encodeToString(MovementUpdate.serializer(), MovementUpdate("2026-09-01", "x", d("1"), "expense", "Otros"))) as JsonObject
        val create = json.parseToJsonElement(json.encodeToString(EntryCreate.serializer(), EntryCreate(d("1"), "x", "Otros", "2026-09-01"))) as JsonObject
        for (body in listOf(update, create)) {
            assertFalse(body.toString(), "currency" in body || "exchange_rate" in body || "original_amount" in body || "original_currency" in body)
        }
    }

    // --- Rows whose PUT would erase original_* stay read-only. -------------------------------

    @Test fun rowsWithCurrencyDataOrNoDateAreReadOnly() {
        fun row(extra: String, date: String? = "\"2026-09-01\"") = json.decodeFromString<Movement>(
            """{"movement_id":"expense:1","transaction_date":$date,"amount":5200,"transaction_type":"expense","editable":true$extra}""",
        )
        assertTrue(row("").isEditable)
        assertTrue(row("", "\"2026-09-01T12:00:00\"").isEditable)
        assertFalse("another currency", row(""","original_amount":10,"original_currency":"USD","exchange_rate":520""").isEditable)
        assertFalse("currency equal to the base", row(""","original_amount":5200,"original_currency":"CRC"""").isEditable)
        assertFalse("only the rate", row(""","exchange_rate":520""").isEditable)
        assertFalse("only the typed amount", row(""","original_amount":10""").isEditable)
        assertFalse("only the currency", row(""","original_currency":"usd"""").isEditable)
        assertFalse("only the base currency", row(""","original_currency":"CRC"""").isEditable)
        assertFalse("no date", row("", "null").isEditable)
        assertFalse("unusable date", row("", "\"septiembre\"").isEditable)
        assertFalse("backend says no", row(""","editable":false""".replace(",\"editable\":false", "")).copy(editable = false).isEditable)
        assertEquals(0, d("520").compareTo(row(""","exchange_rate":520""").exchangeRate))
    }

    // --- Launch policy: never silent fixtures, never fixtures in release, HTTPS only. --------

    private val https = "https://api.example.test"
    private val supabase = "https://project.example.test"

    @Test fun releaseNeverRunsOnFixtures() {
        for (launch in listOf("POPULATED", "empty", "")) for (optIn in listOf(true, false)) {
            val decision = LaunchPolicy.decide(false, launch, optIn, https, supabase, "anon")
            assertTrue("$launch/$optIn → $decision", decision is LaunchPolicy.Decision.Live)
            assertEquals(LaunchPolicy.Decision.Unconfigured(LaunchPolicy.Reason.MISSING), LaunchPolicy.decide(false, launch, optIn, "", "", ""))
        }
    }

    @Test fun missingConfigurationNeverFallsBackToFixtures() {
        for (debug in listOf(true, false)) for ((api, url, key) in listOf(Triple("", supabase, "anon"), Triple(https, " ", "anon"), Triple(https, supabase, ""), Triple(null, null, null))) {
            assertEquals(LaunchPolicy.Decision.Unconfigured(LaunchPolicy.Reason.MISSING), LaunchPolicy.decide(debug, null, false, api, url, key))
        }
    }

    @Test fun debugFixturesOnlyWhenAskedFor() {
        assertEquals(LaunchPolicy.Decision.Fixtures("EMPTY"), LaunchPolicy.decide(true, "EMPTY", false, "", "", ""))
        assertEquals(LaunchPolicy.Decision.Fixtures(null), LaunchPolicy.decide(true, null, true, https, supabase, "anon"))
        assertTrue(LaunchPolicy.decide(true, null, false, https, supabase, "anon") is LaunchPolicy.Decision.Live)
    }

    @Test fun backendMustBeHttps() {
        val insecure = LaunchPolicy.Decision.Unconfigured(LaunchPolicy.Reason.INSECURE_URL)
        val invalid = LaunchPolicy.Decision.Unconfigured(LaunchPolicy.Reason.INVALID_URL)
        assertEquals(insecure, LaunchPolicy.decide(false, null, false, "http://api.example.test", supabase, "anon"))
        assertEquals(insecure, LaunchPolicy.decide(false, null, false, https, "http://project.example.test", "anon"))
        assertEquals(insecure, LaunchPolicy.decide(false, null, false, "http://10.0.2.2:8000", supabase, "anon"))
        assertEquals(insecure, LaunchPolicy.decide(true, null, false, "http://api.example.test", supabase, "anon"))
        assertEquals(insecure, LaunchPolicy.decide(true, null, false, "ftp://api.example.test", supabase, "anon"))
        assertTrue(LaunchPolicy.decide(true, null, false, "http://10.0.2.2:8000", "http://localhost:54321", "anon") is LaunchPolicy.Decision.Live)
        assertEquals(invalid, LaunchPolicy.decide(false, null, false, "https://user:pw@api.example.test", supabase, "anon"))
        assertEquals(invalid, LaunchPolicy.decide(false, null, false, "https:///nohost", supabase, "anon"))
        assertEquals(invalid, LaunchPolicy.decide(false, null, false, "not a url", supabase, "anon"))
        assertEquals(invalid, LaunchPolicy.decide(false, null, false, "https://api.example.test/?next=http://x", supabase, "anon"))
    }

    // --- Session isolation: a refresh never lands on another session. ------------------------

    /** Holds every request until [release]; then answers with [response]. */
    private class GatedTransport(private val response: HttpResponse) : HttpTransport {
        val started = CompletableDeferred<Unit>()
        private val gate = CompletableDeferred<Unit>()
        var calls = 0
        fun release() = gate.complete(Unit)
        override suspend fun send(request: HttpRequest): HttpResponse {
            calls += 1
            started.complete(Unit)
            gate.await()
            return response
        }
    }

    private fun fresh(token: String, refresh: String) =
        HttpResponse(200, """{"access_token":"$token","refresh_token":"$refresh","expires_in":3600,"user":{"id":"u1"}}""")
    private val sessionA = AuthSession("a-old", "ra", 0, "user-a")
    private val sessionB = AuthSession("b-live", "rb", Long.MAX_VALUE / 2, "user-b")

    @Test fun signOutDuringRefreshStaysSignedOut() = runTest {
        val transport = GatedTransport(fresh("a-new", "ra2"))
        val store = InMemorySessionStore(sessionA)
        var signedOutCalls = 0
        val manager = SessionManager(SupabaseAuthClient("https://p.example.test", "anon", transport), store) { signedOutCalls += 1 }
        val request = async { runCatching { manager.accessToken(false) } }
        transport.started.await()
        store.clear() // what signOut() does first; the network logout is best effort
        transport.release()
        val result = request.await()
        assertTrue(result.exceptionOrNull().toString(), result.exceptionOrNull() is AuthException.SessionChanged)
        assertNull("the old session's refresh must not sign it back in", store.load())
        assertEquals(0, signedOutCalls)
    }

    @Test fun anotherSignInDuringRefreshKeepsTheNewSession() = runTest {
        val transport = GatedTransport(fresh("a-new", "ra2"))
        val store = InMemorySessionStore(sessionA)
        val manager = SessionManager(SupabaseAuthClient("https://p.example.test", "anon", transport), store)
        val requestA = async { runCatching { manager.accessToken(false) } }
        transport.started.await()
        manager.accept(sessionB)
        // B does not wait for A's refresh and gets B's own token.
        assertEquals("b-live", manager.accessToken(false))
        transport.release()
        assertTrue(requestA.await().exceptionOrNull() is AuthException.SessionChanged)
        assertEquals(sessionB, store.load())
    }

    /** Holds requests carrying [heldRefreshToken] until [release]; answers the others at once. */
    private class RoutingTransport(private val heldRefreshToken: String) : HttpTransport {
        val held = CompletableDeferred<Unit>()
        private val gate = CompletableDeferred<Unit>()
        fun release() = gate.complete(Unit)
        override suspend fun send(request: HttpRequest): HttpResponse {
            val refresh = Regex(""""refresh_token":"([^"]+)"""").find(request.body.orEmpty())?.groupValues?.get(1)
            if (refresh == heldRefreshToken) { held.complete(Unit); gate.await() }
            return HttpResponse(200, """{"access_token":"$refresh-access","refresh_token":"$refresh-next","expires_in":3600,"user":{"id":"u"}}""")
        }
    }

    @Test fun anotherSessionNeverAwaitsTheOldRefresh() = runTest {
        val transport = RoutingTransport(heldRefreshToken = "ra")
        val store = InMemorySessionStore(sessionA)
        val manager = SessionManager(SupabaseAuthClient("https://p.example.test", "anon", transport), store)
        val requestA = async { runCatching { manager.accessToken(false) } }
        transport.held.await()
        manager.accept(AuthSession("b-old", "rb", 0, "user-b"))
        // B's own expired session refreshes on its own; it never waits for, or receives, A's.
        val tokenB = kotlinx.coroutines.withTimeout(5_000) { manager.accessToken(false) }
        assertEquals("rb-access", tokenB)
        transport.release()
        assertTrue(requestA.await().exceptionOrNull() is AuthException.SessionChanged)
        assertEquals("rb-next", store.load()?.refreshToken)
    }

    @Test fun rejectedRefreshOfAnOldSessionDoesNotSignOutTheNewOne() = runTest {
        val transport = GatedTransport(HttpResponse(400, "{}"))
        val store = InMemorySessionStore(sessionA)
        var signedOutCalls = 0
        val manager = SessionManager(SupabaseAuthClient("https://p.example.test", "anon", transport), store) { signedOutCalls += 1 }
        val requestA = async { runCatching { manager.accessToken(false) } }
        transport.started.await()
        manager.accept(sessionB)
        transport.release()
        assertTrue(requestA.await().exceptionOrNull() is AuthException.SessionChanged)
        assertEquals(sessionB, store.load())
        assertEquals(0, signedOutCalls)
    }

    @Test fun forcedRefreshOfTheSameSessionIsShared() = runTest {
        val transport = GatedTransport(fresh("a-new", "ra2"))
        val store = InMemorySessionStore(sessionA)
        val manager = SessionManager(SupabaseAuthClient("https://p.example.test", "anon", transport), store)
        val first = async { manager.accessToken(true) }
        val second = async { manager.accessToken(true) }
        transport.started.await()
        yield()
        transport.release()
        assertEquals(listOf("a-new", "a-new"), listOf(first.await(), second.await()))
        assertEquals(1, transport.calls)
        assertEquals("ra2", store.load()?.refreshToken)
    }

    @Test fun cancelledCallerStillRecordsTheRotatedToken() = runTest {
        // Supabase rotates the refresh token as soon as it answers; if the caller has gone away,
        // the answer must still be saved, or the device keeps a spent token and is signed out later.
        val transport = GatedTransport(fresh("a-new", "ra2"))
        val store = InMemorySessionStore(sessionA)
        var signedOutCalls = 0
        val manager = SessionManager(SupabaseAuthClient("https://p.example.test", "anon", transport), store) { signedOutCalls += 1 }
        val request = async { manager.accessToken(false) }
        transport.started.await()
        request.cancel()
        transport.release()
        try { request.await(); fail() } catch (_: kotlinx.coroutines.CancellationException) {}
        assertEquals("ra2", store.load()?.refreshToken)
        assertEquals("a-new", manager.accessToken(false))
        assertEquals(1, transport.calls)
        assertEquals(0, signedOutCalls)
    }

    @Test fun transientRefreshAnswersKeepTheSession() = runTest {
        for (status in listOf(302, 408, 425, 429, 500, 503)) {
            val store = InMemorySessionStore(sessionA)
            var signedOutCalls = 0
            val transport = GatedTransport(HttpResponse(status, "{}")).also { it.release() }
            val manager = SessionManager(SupabaseAuthClient("https://p.example.test", "anon", transport), store) { signedOutCalls += 1 }
            try { manager.accessToken(false); fail("$status") } catch (_: ApiError) {}
            assertEquals("$status must not sign out", sessionA, store.load())
            assertEquals(0, signedOutCalls)
        }
        for (status in listOf(400, 401, 403)) {
            val store = InMemorySessionStore(sessionA)
            val transport = GatedTransport(HttpResponse(status, "{}")).also { it.release() }
            val manager = SessionManager(SupabaseAuthClient("https://p.example.test", "anon", transport), store)
            try { manager.accessToken(false); fail("$status") } catch (_: AuthException.SignedOut) {}
            assertNull("$status is a rejected grant", store.load())
        }
    }

    /** Returns [stale] on the first read (what a request saw before another refresh saved). */
    private class StaleOnceStore(private val stale: AuthSession, current: AuthSession) : SessionStore {
        private val real = InMemorySessionStore(current)
        private var first = true
        override fun load(): AuthSession? = if (first) { first = false; stale } else real.load()
        override fun save(session: AuthSession) = real.save(session)
        override fun clear() = real.clear()
    }

    @Test fun aStaleReadUsesTheAlreadyRotatedSession() = runTest {
        val rotated = AuthSession("a-new", "ra2", Long.MAX_VALUE / 2, "user-a")
        val transport = GatedTransport(fresh("never", "never")).also { it.release() }
        val manager = SessionManager(SupabaseAuthClient("https://p.example.test", "anon", transport), StaleOnceStore(sessionA, rotated))
        assertEquals("a-new", manager.accessToken(false))
        assertEquals("a spent refresh token is never replayed", 0, transport.calls)
    }

    @Test fun aStaleReadOfAnotherAccountNeverGetsItsToken() = runTest {
        val transport = GatedTransport(fresh("never", "never")).also { it.release() }
        val manager = SessionManager(SupabaseAuthClient("https://p.example.test", "anon", transport), StaleOnceStore(sessionA, sessionB))
        try { manager.accessToken(false); fail() } catch (_: AuthException.SessionChanged) {}
        assertEquals(0, transport.calls)
    }

    @Test fun signOutClearsBeforeTheNetworkCall() = runTest {
        val transport = GatedTransport(HttpResponse(204, ""))
        val store = InMemorySessionStore(sessionB)
        val manager = SessionManager(SupabaseAuthClient("https://p.example.test", "anon", transport), store)
        val signOut = async { manager.signOut() }
        transport.started.await()
        assertNull("no request may use the session while Supabase is told", store.load())
        try { manager.accessToken(false); fail() } catch (_: AuthException.SignedOut) {}
        transport.release()
        signOut.await()
    }

    // --- Network: no redirects, so a bearer token is never replayed elsewhere. ---------------

    @Test fun transportFollowsNoRedirects() {
        val client = OkHttpTransport.defaultClient()
        assertFalse(client.followRedirects)
        assertFalse(client.followSslRedirects)
        assertEquals(20_000, client.callTimeoutMillis)
    }
}
