package com.dincr.data

import java.math.BigDecimal
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * "Pagado con" on manual expenses: a create sends the account only when chosen, an edit leaves the
 * stored link alone unless it is changed (null clears it), and only own accounts are offered.
 * iOS: `PaidWithTests`.
 */
class PaidWithTest {
    private fun backend() = FakeBackend(FakeBackend.Scenario.POPULATED, PlanTier.VIP)
    private fun api(backend: FakeBackend) = DincrApi(ApiClient("https://fixtures.invalid", { "t" }, backend, AppLanguage.SPANISH, backoff = {}))
    private fun sent(backend: FakeBackend) = Json.parseToJsonElement(backend.requests.last().body!!).jsonObject
    private fun update(amount: Int = 5000) = MovementUpdate("2026-10-20", "Almuerzo con cuenta", BigDecimal(amount), "expense", "Comida")

    @Test fun anEditSendsTheKeyOnlyWhenTheLinkChanges() = runTest {
        val backend = backend()
        val api = api(backend)
        val own = api.paidWithOptions().offered.first()
        api.create(MovementKind.EXPENSE, EntryCreate(BigDecimal(4500), "Almuerzo con cuenta", "Comida", "2026-10-20", financialAccountId = own.id), IdempotencyKey.new())
        assertEquals(own.id.toString(), sent(backend)["financial_account_id"]!!.jsonPrimitive.content)
        val created = api.movements().first { it.description == "Almuerzo con cuenta" }
        assertEquals(own.id, created.financialAccountId)

        api.update(created.movementId, update())
        assertFalse("an untouched link is not sent", sent(backend).containsKey("financial_account_id"))
        assertEquals(own.id, api.movements().first { it.movementId == created.movementId }.financialAccountId)

        api.update(created.movementId, update(), PaidWithChange.Set(null))
        assertEquals(JsonNull, sent(backend)["financial_account_id"])
        assertNull(api.movements().first { it.movementId == created.movementId }.financialAccountId)
    }

    @Test fun aCreateWithoutAChoiceSendsNoKey() = runTest {
        val backend = backend()
        api(backend).create(MovementKind.EXPENSE, EntryCreate(BigDecimal(4500), "Pan", "Comida", null), IdempotencyKey.new())
        assertFalse(sent(backend).containsKey("financial_account_id"))
    }

    @Test fun onlyOwnAccountsAreOfferedAndAccepted() = runTest {
        val api = api(backend())
        val offered = api.paidWithOptions().offered
        assertTrue(offered.isNotEmpty() && offered.none { it.id == 1L })  // account 1 is pending
        val status = try {
            api.create(MovementKind.EXPENSE, EntryCreate(BigDecimal(1), "x", "Comida", null, financialAccountId = 1), IdempotencyKey.new()); null
        } catch (e: ApiError) { e.status }
        assertEquals(409, status)
    }

    @Test fun nothingIsOfferedWhileUnavailable() {
        val json = """{"status":"ok","available":false,"items":[{"id":2,"account_name":"Tarjeta","bank_name":"BAC","account_type":"credit_card","account_last4":"5678","currency":"USD"}]}"""
        val options = Json { ignoreUnknownKeys = true }.decodeFromString(PaidWithOptions.serializer(), json)
        assertTrue(options.offered.isEmpty())
        assertEquals("BAC · Tarjeta ••5678", options.items.single().label)
    }
}
