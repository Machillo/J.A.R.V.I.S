package com.dincr.data

import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/**
 * A credit card's statement cut day (Cuentas): only own credit cards take one, a cleared day is an
 * explicit null, and the server's "not available yet" is kept. iOS: `StatementCutDayTests`.
 */
class StatementCutDayTest {
    private fun backend() = FakeBackend(FakeBackend.Scenario.POPULATED, PlanTier.VIP)
    private fun api(backend: FakeBackend) = DincrApi(ApiClient("https://fixtures.invalid", { "t" }, backend, AppLanguage.SPANISH, backoff = {}))
    private fun sent(backend: FakeBackend) = Json.parseToJsonElement(backend.requests.last().body!!).jsonObject

    private suspend fun status(block: suspend () -> Unit): Int? =
        try { block(); null } catch (e: ApiError) { e.status }

    @Test fun theRequestAlwaysSendsTheKeyEvenToClearIt() = runTest {
        val backend = backend()
        val api = api(backend)
        status { api.setStatementCutDay(2, 21) }
        assertEquals("21", sent(backend)["statement_cut_day"]!!.jsonPrimitive.content)
        assertTrue(backend.requests.last().url.endsWith("/financial-identity/accounts/2/statement-cut-day"))
        status { api.setStatementCutDay(2, null) }
        assertTrue("the key travels as null", sent(backend).containsKey("statement_cut_day"))
        assertEquals(JsonNull, sent(backend)["statement_cut_day"])
    }

    @Test fun theListingCarriesTheDayAndWhetherItIsAvailable() {
        val json = """{"status":"ok","statement_cut_day_available":false,"items":[{"id":2,"account_type":"credit_card","ownership_status":"own","statement_cut_day":null}]}"""
        val identity = Json { ignoreUnknownKeys = true }.decodeFromString(FinancialIdentity.serializer(), json)
        assertFalse(identity.statementCutDayAvailable)
        assertNull(identity.items.single().statementCutDay)
        assertTrue(identity.items.single().takesCutDay)
        assertFalse("an older server without the flag hides the control", Json { ignoreUnknownKeys = true }.decodeFromString(FinancialIdentity.serializer(), """{"items":[]}""").statementCutDayAvailable)
    }

    @Test fun onlyOwnCreditCardsTakeACutDay() {
        fun account(type: String, ownership: String) = FinancialIdentity.Account(1, accountType = type, ownershipStatus = ownership)
        assertTrue(account("credit_card", "own").takesCutDay)
        assertFalse(account("credit_card", "pending").takesCutDay)
        assertFalse(account("checking", "own").takesCutDay)
    }

    @Test fun theFakeRefusesWhatTheBackendRefuses() = runTest {
        val api = api(backend())
        assertTrue(api.financialIdentity().statementCutDayAvailable)
        // The sample accounts are a checking and a savings account: neither takes a cut day.
        assertEquals(422, status { api.setStatementCutDay(2, 21) })
        assertEquals(404, status { api.setStatementCutDay(999, 21) })
        if (api.financialIdentity().items.any { it.statementCutDay != null }) fail("a refused request changed nothing")
    }
}
