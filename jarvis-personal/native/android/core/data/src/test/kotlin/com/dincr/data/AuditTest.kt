package com.dincr.data

import java.io.IOException
import java.math.BigDecimal
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/**
 * Money input/format and contract cases from the C4 audit. The Swift twin is `AuditTests` in
 * DincrKit: both platforms must give the same answers.
 */
class AuditTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }
    private fun d(value: String) = BigDecimal(value)

    private val dotComma = listOf(
        "1" to d("1"), "1.5" to null, "1,5" to d("1.5"), "1,000" to null, "1.000" to d("1000"),
        "1,000.50" to null, "1.000,50" to d("1000.5"), "₡1.000" to null, "$1,000.50" to null,
        " 18 450 " to d("18450"), "-5" to null, "0" to null, "0,00" to null, "" to null, "abc" to null, "NaN" to null,
        "Infinity" to null, "1e5" to null, "999.999.999.999,99" to d("999999999999.99"),
        "1.000.000.000.000" to null, "12,345" to null,
    )
    private val commaDot = listOf(
        "1" to d("1"), "1.5" to d("1.5"), "1,5" to null, "1,000" to d("1000"), "1.000" to null,
        "1,000.50" to d("1000.5"), "1.000,50" to null, "₡1.000" to null, "$1,000.50" to null,
        " 18 450 " to d("18450"), "-5" to null, "0" to null, "0.00" to null, "" to null, "abc" to null, "NaN" to null,
        "Infinity" to null, "1e5" to null, "999,999,999,999.99" to d("999999999999.99"),
        "1,000,000,000,000" to null, "12.345" to null,
    )

    private fun check(cases: List<Pair<String, BigDecimal?>>, separators: MoneyFormat.Separators) = cases.forEach { (text, expected) ->
        val actual = AmountInput.parse(text, separators)
        if (expected == null) assertNull("\"$text\" must be rejected", actual)
        else assertEquals("\"$text\"", 0, expected.compareTo(actual))
    }

    @Test fun dotCommaInput() = check(dotComma, MoneyFormat.Separators.DOT_COMMA)
    @Test fun commaDotInput() = check(commaDot, MoneyFormat.Separators.COMMA_DOT)

    @Test fun inputTextRoundTripsExactly() {
        listOf(
            Triple(MoneyFormat("CRC", MoneyFormat.Separators.DOT_COMMA), d("18450.5"), "18.450,5"),
            Triple(MoneyFormat("CRC", MoneyFormat.Separators.COMMA_DOT), d("12345.5"), "12,345.5"),
            Triple(MoneyFormat("USD", MoneyFormat.Separators.COMMA_DOT), d("1234.56"), "1,234.56"),
            Triple(MoneyFormat("CRC", MoneyFormat.Separators.DOT_COMMA), d("1000000"), "1.000.000"),
            Triple(MoneyFormat("USD", MoneyFormat.Separators.DOT_COMMA), d("999999999999.99"), "999.999.999.999,99"),
        ).forEach { (format, amount, text) ->
            assertEquals(text, format.inputText(amount))
            assertEquals(0, amount.compareTo(AmountInput.parse(format.inputText(amount), format.separators)))
        }
    }

    @Test fun displayRoundsHalfAwayFromZeroLikeTheWebApp() {
        val crc = MoneyFormat()
        assertEquals("₡3", crc.format(d("2.5")))
        assertEquals("₡1.235", crc.format(d("1234.6")))
        assertEquals("−₡1.235", crc.format(d("-1234.5")))
        assertEquals("₡0", crc.format(BigDecimal.ZERO))
        assertEquals("$1,234.60", MoneyFormat("USD", MoneyFormat.Separators.COMMA_DOT).format(d("1234.6")))
        assertEquals("−$0.01", MoneyFormat("USD", MoneyFormat.Separators.COMMA_DOT).format(d("-0.005")))
        assertEquals("1.234,60 €", MoneyFormat("EUR", MoneyFormat.Separators.DOT_COMMA, MoneyFormat.Placement.AFTER).format(d("1234.6")))
        // Legacy base currencies keep their code, never converted and never shown as ₡ or $.
        assertEquals("ARS 1.234,00", MoneyFormat("ARS").format(d("1234")))
    }

    @Test fun spokenAmountNamesTheCurrencyShown() {
        val crc = MoneyFormat()
        assertEquals("1234.5 dollars", crc.spoken(d("1234.5"), language = AppLanguage.ENGLISH, currencyOverride = "USD"))
        assertEquals("1235 colones", crc.spoken(d("1234.5"), language = AppLanguage.ENGLISH))
        assertEquals("2 euros", MoneyFormat("EUR").spoken(d("2"), language = AppLanguage.SPANISH))
    }

    @Test fun decodesTheRealIdentityShape() {
        val profile = json.decodeFromString<Profile>(checkNotNull(javaClass.getResource("/me.json")).readText())
        assertEquals("allowed_users.id is an integer", 4201L, profile.id)
        assertEquals(true, profile.profileSetupCompleted)
        assertEquals(true, profile.planSelected)
    }

    @Test fun missingGateFlagsStayUnknown() {
        val profile = json.decodeFromString<Profile>("""{"id":1}""")
        assertNull(profile.profileSetupCompleted)
        assertNull(profile.planSelected)
        assertNull(profile.role)
        assertFalse(profile.isOwner)
    }

    @Test fun moneyDecodesWithoutBinaryRounding() {
        val rows = json.decodeFromString<List<Movement>>(
            """[{"movement_id":"expense:1","amount":999999999999.99,"transaction_type":"expense","editable":true},{"movement_id":"expense:2","amount":0.1,"transaction_type":"expense","editable":true}]""",
        )
        assertEquals(0, d("999999999999.99").compareTo(rows[0].amount))
        assertEquals(0, d("0.1").compareTo(rows[1].amount))
    }

    @Test fun rowsTypedInAnotherCurrencyAreReadOnlyHere() {
        val row = json.decodeFromString<Movement>("""{"movement_id":"expense:1","amount":5200,"transaction_type":"expense","editable":true,"original_amount":10,"original_currency":"USD"}""")
        assertFalse(row.isEditable("CRC"))
        assertTrue(row.isEditable("usd"))
        assertTrue(json.decodeFromString<Movement>("""{"movement_id":"expense:2","amount":1,"transaction_type":"expense","editable":true}""").isEditable("CRC"))
    }

    @Test fun dashboardIgnoresUnknownFields() {
        assertEquals("2026-09", json.decodeFromString<FreeDashboard>("""{"month":"2026-09","income":1,"expenses":1,"categories":[],"monthly_history":[],"future_field":{"x":1}}""").month)
    }

    @Test fun errorDetailMayBeAListOrAnObject() {
        val list = ApiError.from(422, """{"detail":[{"loc":["body","amount"],"msg":"x"}]}""", AppLanguage.SPANISH, null)
        assertEquals(ApiError.Kind.VALIDATION, list.kind)
        assertEquals("Revisá la información e intentá nuevamente.", list.message)
        val obj = ApiError.from(409, """{"detail":{"code":"account_deletion_pending","message":"Tu cuenta se está eliminando."}}""", AppLanguage.ENGLISH, null)
        assertEquals("account_deletion_pending", obj.code)
        assertEquals("Tu cuenta se está eliminando.", obj.message)
        assertEquals(ApiError.Kind.SUBSCRIPTION_REQUIRED, ApiError.from(402, "", AppLanguage.SPANISH, null).kind)
        assertEquals(ApiError.Kind.SERVER, ApiError.from(503, """{"detail":"x","code":"feature_temporarily_unavailable"}""", AppLanguage.SPANISH, null).kind)
    }

    @Test fun createsCarryTheIdempotencyKeyAndAreNeverRetried() = runTest {
        val requests = mutableListOf<HttpRequest>()
        val transport = HttpTransport { request -> requests += request; HttpResponse(503, "{}") }
        val client = ApiClient("https://api.example.test", { "t" }, transport, AppLanguage.SPANISH, backoff = {})
        try { LiveDincrService(client).create(MovementKind.EXPENSE, EntryCreate(BigDecimal.ONE, "x", "Comida", null), "key-12345678"); fail() } catch (_: ApiError) {}
        assertEquals(1, requests.size)
        assertEquals("key-12345678", requests.single().headers["X-Idempotency-Key"])
        assertEquals("https://api.example.test/user-product/finance/expenses", requests.single().url)
    }

    @Test fun networkLossOnAWriteIsReportedNotRetried() = runTest {
        var calls = 0
        val client = ApiClient("https://api.example.test", { "t" }, { calls += 1; throw IOException("lost") }, AppLanguage.SPANISH, backoff = {})
        try { client.perform("DELETE", "/user-product/free/movements/expense:1", emptyMap(), null); fail() } catch (e: ApiError) { assertEquals(ApiError.Kind.OFFLINE, e.kind) }
        assertEquals(1, calls)
    }

    @Test fun fixtureServiceMirrorsBackendWriteSemantics() = runTest {
        val service = FixtureDincrService(FixtureDincrService.Scenario.EMPTY, latencyMs = 0)
        val entry = EntryCreate(BigDecimal.ONE, "x", "Comida", "2026-09-25")
        service.create(MovementKind.EXPENSE, entry, "same-key-1")
        service.create(MovementKind.EXPENSE, entry, "same-key-1")
        val rows = service.movements()
        assertEquals("a replayed key must not add a second row", 1, rows.size)
        service.delete(rows.single().movementId)
        try { service.delete(rows.single().movementId); fail() } catch (e: ApiError) { assertEquals(ApiError.Kind.NOT_FOUND, e.kind) }
    }

    @Test fun searchIgnoresCaseAndAccents() {
        assertTrue(SearchText.matches("credito", listOf("Pago de Crédito")))
        assertTrue(SearchText.matches("  CAFÉ ", listOf(null, "cafe")))
        assertTrue(SearchText.matches("", listOf(null)))
        assertFalse(SearchText.matches("alquiler", listOf("Supermercado", null)))
    }
}
