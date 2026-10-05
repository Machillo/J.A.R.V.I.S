package com.dincr.data

import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * UX-4 — debts are managed in Plan → Deudas. Opening them reads the list and nothing else, and a
 * percentage the backend can't know (no original amount) is never shown as 0 % paid. The Swift twin
 * is `DebtsInPlanTests`.
 */
class DebtsInPlanTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }

    /** The debts screen's only request is this GET (its other request is screen analytics, not money). */
    @Test fun theDebtsListIsReadWithASingleGet() = runTest {
        for (plan in PlanTier.entries) {
            val backend = FakeBackend(FakeBackend.Scenario.POPULATED, plan)
            val api = DincrApi(ApiClient("https://fixtures.invalid", { "t" }, backend, AppLanguage.SPANISH, backoff = {}))
            val before = backend.requests.size
            api.debts()
            val sent = backend.requests.drop(before)
            assertEquals("$plan", listOf("GET"), sent.map { it.method })
            assertTrue("$plan", sent.single().url.endsWith("/user-product/finance/debts"))
            // No payment, no installment application, no other write.
            assertTrue(sent.none { "payments" in it.url || "apply-due-installments" in it.url })
        }
    }

    @Test fun everyPlanCanManageItsDebts() {
        // The Plan row's gate (`debts`) is Free: everyone can record and keep their real debts.
        PlanTier.entries.forEach { assertTrue("$it", it.allows(Feature.DEBTS)) }
    }

    @Test fun progressIsShownOnlyFromAKnownOriginalAmount() {
        fun debt(raw: String) = json.decodeFromString<Debt>(raw)
        assertEquals(40.0, debt("""{"id":1,"total_amount":500000,"remaining_amount":300000,"progress_percent":40.0}""").knownProgressPercent!!, 0.0)
        // The list answers 0 % when the original amount is unknown: that is not a fact about the debt.
        assertNull(debt("""{"id":2,"total_amount":null,"remaining_amount":300000,"progress_percent":0}""").knownProgressPercent)
        assertNull(debt("""{"id":3,"total_amount":0,"remaining_amount":0,"progress_percent":0}""").knownProgressPercent)
        assertEquals(100.0, debt("""{"id":4,"total_amount":100,"remaining_amount":0,"progress_percent":100}""").knownProgressPercent!!, 0.0)
    }

    @Test fun aTotalIsShownOnlyWhenEveryDebtHasTheFigure() {
        fun bd(value: Long) = java.math.BigDecimal.valueOf(value)
        assertEquals(bd(450), Debt.knownSum(listOf(bd(300), bd(150))))
        assertNull(Debt.knownSum(listOf(bd(300), null)))          // never 300 + 0
        assertEquals(java.math.BigDecimal.ZERO, Debt.knownSum(emptyList()))
    }

    @Test fun unknownFiguresStayUnknown() {
        val debt = json.decodeFromString<Debt>("""{"id":5,"name":"Préstamo","remaining_amount":null}""")
        assertNull(debt.remainingAmount)
        assertNull(debt.monthlyPayment)
        assertNull(debt.nextPaymentDate)
    }
}
