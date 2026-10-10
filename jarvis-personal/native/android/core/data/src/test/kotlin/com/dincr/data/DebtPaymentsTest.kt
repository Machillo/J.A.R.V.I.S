package com.dincr.data

import java.math.BigDecimal
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * DEB-07a — a debt's payment history: the backend's shape decodes, and the fixture records each
 * payment with the amount actually applied (capped at the balance), newest first. The Swift twin is
 * `DebtPaymentsTests`. Synthetic data.
 */
class DebtPaymentsTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }

    @Test fun aPaymentDecodesTheBackendsShape() {
        val payments = json.decodeFromString<List<DebtPayment>>("""[{"id":7,"payment_date":"2026-10-09","amount":70000.0},{"id":3,"payment_date":"2026-10-01","amount":null}]""")
        assertEquals(listOf(7L, 3L), payments.map { it.id })
        assertEquals("2026-10-09", payments.first().paymentDate)
        assertEquals(0, BigDecimal(70000).compareTo(payments.first().amount))
        assertNull("an unknown amount stays unknown", payments.last().amount)
    }

    @Test fun theFixtureListsEachPaymentNewestFirstWithTheAmountApplied() = runTest {
        val api = DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(FakeBackend.Scenario.POPULATED), AppLanguage.SPANISH, backoff = {}))
        val debt = api.debts().first { (it.remainingAmount ?: BigDecimal.ZERO).signum() > 0 }
        val remaining = debt.remainingAmount!!
        assertTrue(api.debtPayments(debt.id).isEmpty())
        api.payDebt(debt.id, BigDecimal(1000), "pay-1")
        api.payDebt(debt.id, remaining.multiply(BigDecimal(2)), "pay-2")
        val payments = api.debtPayments(debt.id)
        assertEquals("newest first; the second payment is capped at the balance",
            listOf(remaining - BigDecimal(1000), BigDecimal(1000)).map { it.stripTrailingZeros() }, payments.map { it.amount!!.stripTrailingZeros() })
    }
}
