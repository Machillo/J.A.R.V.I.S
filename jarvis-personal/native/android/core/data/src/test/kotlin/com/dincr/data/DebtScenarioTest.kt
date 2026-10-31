package com.dincr.data

import java.math.BigDecimal
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/**
 * Debt what-ifs (VIP): the request the backend expects, unknown values kept unknown, and the fake
 * backend's VIP gate and errors. The Swift twin is `DebtScenarioTests`.
 */
class DebtScenarioTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }

    private fun fake(plan: PlanTier) =
        DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(FakeBackend.Scenario.POPULATED, plan), AppLanguage.SPANISH, backoff = {}))

    @Test fun requestsAreSnakeCaseWithoutEmptyFields() {
        val payOff = json.parseToJsonElement(json.encodeToString(DebtScenarioRequest.serializer(), DebtScenarioRequest.payOff(7))).jsonObject
        assertEquals(setOf("kind", "debt_id"), payOff.keys)
        val newDebt = json.parseToJsonElement(json.encodeToString(DebtScenarioRequest.serializer(),
            DebtScenarioRequest.newDebt("Moto", BigDecimal(1_200_000), null, BigDecimal(24), 24))).jsonObject
        assertEquals(setOf("kind", "amount", "annual_rate", "term_months", "name"), newDebt.keys)
    }

    @Test fun unknownFiguresDecodeAsNullNeverZero() {
        val result = json.decodeFromString(DebtScenarioResult.serializer(), """
            {"kind":"extra_payment","debt":{"id":2,"name":"Préstamo","remaining_amount":2400000,"monthly_payment":100000,"interest_rate":null},
             "monthly_leftover":{"current":null,"scenario":null,"change":null},"one_time_amount":600000,"liquid_savings_after":null,
             "options":{"lower_installment":{"monthly_payment":null,"monthly_leftover":null,"change":null},
                        "shorter_term":{"monthly_payment":100000,"monthly_leftover":null,"months_saved":null,"interest_saved":null}},
             "payoff":null,"warnings":["Esta deuda no tiene tasa de interés conocida."],"explanation":"Tu banco decide."}
        """.trimIndent())
        assertNull(result.monthlyLeftover.current)
        assertNull(result.options?.lowerInstallment?.monthlyPayment)
        assertEquals(0, BigDecimal(100000).compareTo(result.options?.shorterTerm?.monthlyPayment))
        assertNull(result.liquidSavingsAfter)
        assertNull(result.debt?.interestRate)
    }

    @Test fun theFakeAnswersEachScenarioForVip() = runTest {
        val api = fake(PlanTier.VIP)
        val debt = api.debts().first { (it.monthlyPayment?.signum() ?: 0) > 0 && (it.remainingAmount?.signum() ?: 0) > 0 }
        val payOff = api.debtScenario(DebtScenarioRequest.payOff(debt.id))
        assertEquals(0, debt.monthlyPayment!!.compareTo(payOff.monthlyLeftover.change))
        assertEquals(0, debt.remainingAmount!!.compareTo(payOff.oneTimeAmount))
        val extra = api.debtScenario(DebtScenarioRequest.extraPayment(debt.id, BigDecimal(10_000)))
        assertEquals(0, debt.monthlyPayment!!.compareTo(extra.options?.shorterTerm?.monthlyPayment))
        assertTrue(extra.options!!.lowerInstallment!!.monthlyPayment!! < debt.monthlyPayment)
        val newDebt = api.debtScenario(DebtScenarioRequest.newDebt(null, BigDecimal(120_000), BigDecimal(10_000), null, null))
        assertEquals(0, BigDecimal(-10_000).compareTo(newDebt.monthlyLeftover.change))
    }

    /** DS-2: refinance one debt / consolidate several: today against the new loan. */
    @Test fun refinanceAndConsolidateCompareTodayWithTheNewLoan() = runTest {
        val request = DebtScenarioRequest.consolidate(listOf(1, 2), BigDecimal(15), 48, BigDecimal(20_000))
        val body = json.encodeToString(DebtScenarioRequest.serializer(), request)
        assertTrue(body, body.contains("\"kind\":\"consolidate\"") && body.contains("\"debt_ids\":[1,2]"))
        val api = fake(PlanTier.VIP)
        val together = api.debtScenario(request)
        assertEquals(0, BigDecimal(95_000).compareTo(together.comparison?.current?.monthlyPayment))
        assertEquals(2, together.debts.size)
        assertEquals(48, together.comparison?.scenario?.months)
        val one = api.debtScenario(DebtScenarioRequest.refinance(1, BigDecimal(12), 24, null))
        assertEquals(1L, one.debt?.id)
        expectStatus(422) { api.debtScenario(DebtScenarioRequest.consolidate(listOf(1), BigDecimal(12), 24, null)) }
    }

    @Test fun theFakeRefusesWhatTheBackendRefuses() = runTest {
        expectStatus(403) { fake(PlanTier.FREE).debtScenario(DebtScenarioRequest.payOff(1)) }
        val vip = fake(PlanTier.VIP)
        val debt = vip.debts().first { (it.remainingAmount?.signum() ?: 0) > 0 }
        expectStatus(422) { vip.debtScenario(DebtScenarioRequest.extraPayment(debt.id, debt.remainingAmount!!)) }
        expectStatus(404) { vip.debtScenario(DebtScenarioRequest.payOff(999_999)) }
    }

    private suspend fun expectStatus(status: Int, call: suspend () -> Unit) {
        try {
            call()
            fail("expected HTTP $status")
        } catch (error: ApiError) {
            assertEquals(status, error.status)
        }
    }
}
