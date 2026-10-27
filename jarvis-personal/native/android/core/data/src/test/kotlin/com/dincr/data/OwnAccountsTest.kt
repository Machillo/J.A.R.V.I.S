package com.dincr.data

import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Own accounts from the app: "Es mía / No es mía / No la reconozco" and an own account no notice came
 * from. "No la reconozco" travels as `pending` (never an own account) and comes back with its review
 * date; only the last 4 digits ever leave the device. iOS: `OwnAccountsTests`.
 */
class OwnAccountsTest {
    private fun backend() = FakeBackend(FakeBackend.Scenario.POPULATED, PlanTier.VIP)
    private fun api(backend: FakeBackend) = DincrApi(ApiClient("https://fixtures.invalid", { "t" }, backend, AppLanguage.SPANISH, backoff = {}))
    private fun sent(backend: FakeBackend) = Json.parseToJsonElement(backend.requests.last().body!!).jsonObject

    @Test fun eachAnswerTravelsAsTheBackendsStatus() = runTest {
        val backend = backend()
        val api = api(backend)
        val id = api.financialIdentity().items.first().id
        for ((answer, wire) in listOf(AccountOwnership.OWN to "own", AccountOwnership.NOT_MINE to "not_mine", AccountOwnership.UNKNOWN to "pending")) {
            api.setAccountOwnership(id, answer)
            assertEquals(wire, sent(backend)["ownership_status"]!!.jsonPrimitive.content)
        }
    }

    @Test fun notRecognisedIsAReviewedPendingAccountNotAnUnansweredOne() {
        fun account(status: String?, reviewed: String?) = FinancialIdentity.Account(1, ownershipStatus = status, ownershipConfirmedAt = reviewed)
        assertNull(account("pending", null).ownership)
        assertEquals(AccountOwnership.UNKNOWN, account("pending", "2026-10-21T12:00:00Z").ownership)
        assertEquals(AccountOwnership.OWN, account("own", null).ownership)
        assertEquals(AccountOwnership.NOT_MINE, account("not_mine", null).ownership)
    }

    @Test fun aDeclarationSendsOnlyTheLastFourDigitsAndIsReused() = runTest {
        val backend = backend()
        val api = api(backend)
        val first = api.declareOwnAccount(OwnAccountDeclaration.of("multimoney", "", "6281", "USD", "")).item!!
        val body = sent(backend)
        assertEquals("6281", body["account_last4"]!!.jsonPrimitive.content)
        assertFalse("only 'other' carries a name", body.containsKey("institution_name") && body["institution_name"].toString() != "null")
        assertEquals(AccountOwnership.OWN, first.ownership)
        val again = api.declareOwnAccount(OwnAccountDeclaration.of("multimoney", "", "6281", "USD", "")).item!!
        assertEquals(first.id, again.id)
        api.setAccountOwnership(1, AccountOwnership.UNKNOWN)
        val items = api.financialIdentity().items
        assertEquals(AccountOwnership.UNKNOWN, items.first { it.id == 1L }.ownership)
        assertEquals(AccountOwnership.OWN, items.first { it.id == first.id }.ownership)
    }

    @Test fun anIncompleteDeclarationIsNotSent() {
        assertFalse(OwnAccountDeclaration.of("bac", "", "612", "CRC", "").isComplete)
        assertFalse(OwnAccountDeclaration.of("bac", "", "61a1", "CRC", "").isComplete)
        assertFalse(OwnAccountDeclaration.of("other", "  ", "6121", "CRC", "").isComplete)
        assertFalse(OwnAccountDeclaration.of("bac", "", "6121", "EUR", "").isComplete)
        assertTrue(OwnAccountDeclaration.of("other", "Coopealianza", "6121", "CRC", "").isComplete)
    }
}
