package com.dincr.data

import java.math.BigDecimal
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Dollar expenses that wait for the close: a request asks for it only when the editor says so, the
 * colones list leaves them out (never ₡0), and the pending listing totals them per currency.
 * iOS: `PendingConversionTests`.
 */
class PendingConversionTest {
    private fun backend() = FakeBackend(FakeBackend.Scenario.POPULATED, PlanTier.VIP)
    private fun api(backend: FakeBackend) = DincrApi(ApiClient("https://fixtures.invalid", { "t" }, backend, AppLanguage.SPANISH, backoff = {}))
    private fun sent(backend: FakeBackend) = Json.parseToJsonElement(backend.requests.last().body!!).jsonObject
    private fun hotel(amount: String = "120", waits: Boolean = true, rate: BigDecimal? = null) =
        EntryCreate(BigDecimal(amount), "Hotel", "Compras", "2026-10-12", currency = "USD", exchangeRate = rate, convertAtClose = if (waits) true else null)
    private fun status(block: suspend () -> Unit): Int? = try {
        kotlinx.coroutines.runBlocking { block() }; null
    } catch (e: ApiError) { e.status }

    @Test fun theRequestAsksToWaitOnlyWhenTold() = runTest {
        val backend = backend()
        val api = api(backend)
        api.create(MovementKind.EXPENSE, hotel(), IdempotencyKey.new())
        assertEquals("true", sent(backend)["convert_at_close"]!!.jsonPrimitive.content)
        assertFalse(sent(backend).containsKey("exchange_rate"))
        api.create(MovementKind.EXPENSE, hotel(waits = false, rate = BigDecimal(500)), IdempotencyKey.new())
        assertFalse(sent(backend).containsKey("convert_at_close"))
    }

    @Test fun theFixtureKeepsDollarsApartUntilConverted() = runTest {
        val api = api(backend())
        val colones = api.movements()
        api.create(MovementKind.EXPENSE, hotel(), IdempotencyKey.new())
        api.create(MovementKind.EXPENSE, hotel("30.5"), IdempotencyKey.new())
        assertEquals("never a ₡0 row", colones, api.movements())
        val pending = api.pendingConversion()
        assertEquals(2, pending.items.size)
        assertEquals(listOf(PendingConversion.Total("USD", BigDecimal("150.5"), 2)), pending.totals)
        assertTrue(pending.items.all { it.movement.isPendingConversion })

        // The user converts one with their own rate: it joins the colones list and leaves the pending one.
        val first = pending.items.first()
        api.update(first.movementId, MovementUpdate(first.entryDate, "Hotel", first.originalAmount, "expense", "Compras",
            currency = "USD", exchangeRate = BigDecimal(500)))
        assertEquals(1, api.pendingConversion().items.size)
        assertTrue(api.movements().any { it.movementId == first.movementId })
    }

    @Test fun onlyADollarExpenseWithoutARateCanWait() = runTest {
        val api = api(backend())
        assertEquals(422, status { api.create(MovementKind.EXPENSE, hotel(rate = BigDecimal(500)), IdempotencyKey.new()) })
        assertEquals(422, status { api.create(MovementKind.INCOME, hotel(), IdempotencyKey.new()) })
        assertTrue(api.pendingConversion().items.isEmpty())
    }

    @Test fun thePendingListingDecodesWithItsTotals() {
        val body = """{"status":"ok","available":true,"items":[{"movement_id":"expense:9","id":9,"entry_date":"2026-10-12","description":"Hotel",
            "category":"Compras","original_amount":120.5,"original_currency":"USD","financial_account_id":null}],
            "totals":[{"currency":"USD","amount":120.5,"count":1}]}"""
        val pending = Json { ignoreUnknownKeys = true }.decodeFromString(PendingConversion.serializer(), body)
        assertTrue(pending.available)
        assertEquals(BigDecimal("120.5"), pending.items.single().originalAmount)
        assertEquals(PendingConversion.Total("USD", BigDecimal("120.5"), 1), pending.totals.single())
    }
}
