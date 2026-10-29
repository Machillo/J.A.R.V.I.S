package com.dincr.data

import java.math.BigDecimal
import java.time.LocalDate
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test

/**
 * Salvavidas automatic contributions (VIP and the Owner) and the Owner's interest rate: decoding
 * `auto_contribution` / `declared_amount` / `annual_interest_rate`, the PUT body, the client-side
 * checks and the fake's contract (backend: finance/salvavidas_plan.py). Synthetic figures only.
 * iOS: `SalvavidasPlanTests.swift`.
 */
class SalvavidasPlanTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }

    private fun fixture(plan: PlanTier = PlanTier.VIP, role: FakeBackend.Role = FakeBackend.Role.USER, today: LocalDate = LocalDate.of(2026, 10, 29)) =
        FakeBackend(FakeBackend.Scenario.POPULATED, plan, currentDate = today, role = role).let { DincrApi(ApiClient("https://fixtures.invalid", { "t" }, it, AppLanguage.SPANISH, backoff = {})) }

    private suspend fun status(block: suspend () -> Unit): Int = try { block(); 200 } catch (error: ApiError) { error.status }

    @Test fun anEnabledPlanDecodesWithItsBreakdown() {
        val fund = json.decodeFromString<Salvavidas>("""{"status":"OK","scope":"users","current_amount":130000,"current_amount_known":true,"declared_amount":100000,
            "auto_contribution":{"enabled":true,"amount":10000,"frequency":"weekly","start_date":"2026-10-01","end_date":null,"base_amount":100000,
            "base_date":"2026-09-30","contributions_count":3,"contributions_amount":30000,"estimated_interest":0,"next_date":"2026-10-22","total":130000}}""")
        val plan = fund.activePlan!!
        assertEquals(0, BigDecimal(100000).compareTo(fund.declaredAmount))
        assertEquals(0, BigDecimal(130000).compareTo(fund.currentAmount))
        assertEquals("weekly", plan.frequency)
        assertNull(plan.endDate)
        assertEquals(3, plan.contributionsCount)
        assertEquals(0, BigDecimal(30000).compareTo(plan.contributionsAmount))
        assertEquals("2026-10-22", plan.nextDate)
        assertFalse("Users never get the interest rate", fund.offersInterestRate)
        assertNull(fund.annualInterestRate)
    }

    @Test fun noPlanADisabledPlanAndUnknownSavings() {
        val none = json.decodeFromString<Salvavidas>("""{"scope":"users","current_amount":null,"current_amount_known":false,"declared_amount":null,"auto_contribution":null}""")
        assertNull(none.autoContribution)
        assertNull(none.activePlan)
        assertFalse(none.isAmountKnown)
        val disabled = json.decodeFromString<Salvavidas>("""{"scope":"users","current_amount":50000,"current_amount_known":true,"declared_amount":50000,
            "auto_contribution":{"enabled":false,"amount":5000,"frequency":"monthly","start_date":"2026-11-15","end_date":"2027-06-15","contributions_count":0,
            "contributions_amount":0,"estimated_interest":0,"next_date":null,"total":50000}}""")
        assertEquals(false, disabled.autoContribution?.isEnabled)
        assertNull("a disabled plan adds nothing", disabled.activePlan)
        assertEquals("2027-06-15", disabled.autoContribution?.endDate)
        val old = json.decodeFromString<Salvavidas>("""{"scope":"users","current_amount":1000,"current_amount_known":true}""")
        assertNull(old.autoContribution)
        assertNull(old.declaredAmount)
    }

    @Test fun theOwnerGetsTheRateAndTheEstimatedInterest() {
        val fund = json.decodeFromString<Salvavidas>("""{"status":"OK","scope":"owner","current_amount":471234.56,"declared_amount":450000,"annual_interest_rate":2.5,
            "auto_contribution":{"enabled":true,"amount":10000,"frequency":"biweekly","start_date":"2026-09-01","contributions_count":2,"contributions_amount":20000,
            "estimated_interest":1234.56,"next_date":"2026-11-10","total":471234.56}}""")
        assertTrue(fund.offersInterestRate)
        assertEquals(0, BigDecimal("2.5").compareTo(fund.annualInterestRate))
        assertEquals(0, BigDecimal("1234.56").compareTo(fund.activePlan?.estimatedInterest))
    }

    @Test fun thePlanBodyCarriesTheBalanceAndTheOwnerRateOnlyWhenGiven() {
        val plan = SalvavidasPlanRequest(true, BigDecimal(10000), "weekly", "2026-11-05")
        assertEquals("""{"auto_contribution":{"enabled":true,"amount":10000,"frequency":"weekly","start_date":"2026-11-05"}}""", json.encodeToString(SalvavidasUpdate.plan(plan)))
        assertTrue("0 is a valid declared balance", json.encodeToString(SalvavidasUpdate.plan(plan, BigDecimal.ZERO)).contains(""""current_amount":0"""))
        val owner = json.encodeToString(SalvavidasUpdate.plan(SalvavidasPlanRequest(false, BigDecimal(5000), "monthly", "2026-11-05", "2027-05-05"), annualInterestRate = BigDecimal("2.5")))
        assertTrue(owner.contains(""""annual_interest_rate":2.5""") && owner.contains(""""end_date":"2027-05-05"""") && owner.contains(""""enabled":false"""))
        assertFalse("no rate unless the Owner typed one", json.encodeToString(SalvavidasUpdate.plan(plan)).contains("annual_interest_rate"))
        assertNull("nothing to send", SalvavidasUpdate.plan(null))
        assertEquals("""{"annual_interest_rate":3}""", json.encodeToString(SalvavidasUpdate.plan(null, annualInterestRate = BigDecimal(3))))
    }

    @Test fun invalidPlansAndRatesAreRefusedBeforeSending() {
        listOf<() -> Any>(
            { SalvavidasPlanRequest(true, BigDecimal.ZERO, "weekly", "2026-11-05") },
            { SalvavidasPlanRequest(true, BigDecimal(10), "daily", "2026-11-05") },
            { SalvavidasPlanRequest(true, BigDecimal(10), "weekly", "2026-02-30") },
            { SalvavidasPlanRequest(true, BigDecimal(10), "weekly", "2026-11-05", "2026-11-04") },
            { SalvavidasPlanRequest(true, BigDecimal("1000000000"), "weekly", "2026-11-05") },
            { SalvavidasUpdate(annualInterestRate = BigDecimal(51)) },
            { SalvavidasUpdate(annualInterestRate = BigDecimal(-1)) },
        ).forEachIndexed { index, build -> runCatching { build() }.onSuccess { fail("case $index must be refused") } }
        assertNotNull(SalvavidasPlanRequest(true, BigDecimal(10), "weekly", "2026-11-05", "2026-11-05"))
    }

    @Test fun theRateInputAcceptsBothDecimalMarks() {
        assertEquals(0, BigDecimal("2.5").compareTo(SalvavidasRateInput.parse("2,5")))
        assertEquals(0, BigDecimal("2.5").compareTo(SalvavidasRateInput.parse("2.5 %")))
        assertEquals(0, BigDecimal.ZERO.compareTo(SalvavidasRateInput.parse("0")))
        assertEquals(0, BigDecimal(50).compareTo(SalvavidasRateInput.parse("50")))
        listOf("", "50.01", "-1", "abc", "1.23456", "1,2,3", ".5").forEach { assertNull(it, SalvavidasRateInput.parse(it)) }
    }

    @Test fun theFakeMirrorsTheContract() = runTest {
        val api = fixture()
        val plan = SalvavidasPlanRequest(true, BigDecimal(10000), "weekly", "2026-01-01")
        // Unknown savings: enabling needs the balance of today; without a situation it cannot be saved.
        assertEquals(422, status { api.updateSalvavidas(SalvavidasUpdate.plan(plan)!!) })
        assertEquals("the rate is the Owner's alone", 422, status { api.updateSalvavidas(SalvavidasUpdate.plan(null, annualInterestRate = BigDecimal(2))!!) })
        api.updateFinancialSituation(FinancialProfile(incomeType = "fixed", fixedMonthlySalary = BigDecimal(900000), workDaysPerWeek = 5), "k_plan")
        val saved = api.updateSalvavidas(SalvavidasUpdate.plan(plan, BigDecimal.ZERO)!!)
        val active = saved.activePlan!!
        // Declared today: the count starts again from today, so nothing is added yet.
        assertEquals(0, active.contributionsCount)
        assertEquals(0, BigDecimal.ZERO.compareTo(saved.currentAmount))
        assertEquals("2026-11-05", active.nextDate)
        val off = api.updateSalvavidas(SalvavidasUpdate.plan(SalvavidasPlanRequest(false, BigDecimal(10000), "weekly", "2026-01-01"))!!)
        assertNull(off.activePlan)
        assertEquals(0, BigDecimal(10000).compareTo(off.autoContribution?.amount))

        val owner = fixture(role = FakeBackend.Role.OWNER)
        val ownerFund = owner.updateSalvavidas(SalvavidasUpdate.plan(plan, annualInterestRate = BigDecimal("2.5"))!!)
        assertTrue(ownerFund.isOwnerScope)
        assertEquals(0, BigDecimal("2.5").compareTo(ownerFund.annualInterestRate))
        assertNotNull(ownerFund.activePlan)
        assertEquals(0, ownerFund.declaredAmount!!.compareTo(ownerFund.currentAmount))
        // A rate above 50 % is refused by the fake too (the app never sends one).
        val (_, refusal) = FakeSalvavidasPlan(LocalDate.of(2026, 10, 29)).validate(JsonObject(mapOf("annual_interest_rate" to JsonPrimitive(60))), owner = true, balanceKnown = true)
        assertNotNull(refusal)
    }

    @Test fun theFakeCountsContributionsAndInterestLikeTheBackend() {
        val today = LocalDate.of(2026, 10, 22)
        val weekly = Salvavidas.AutoContribution(true, BigDecimal(10000), "weekly", "2026-10-01")
        assertEquals(listOf("2026-10-01", "2026-10-08", "2026-10-15", "2026-10-22"),
            FakeSalvavidasPlan.scheduled(weekly, LocalDate.of(2026, 9, 30), today).map { it.toString() })
        val monthly = Salvavidas.AutoContribution(true, BigDecimal(1), "monthly", "2026-01-31", "2026-04-30")
        assertEquals(listOf("2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"),
            FakeSalvavidasPlan.scheduled(monthly, LocalDate.of(2026, 1, 1), LocalDate.of(2026, 12, 31)).map { it.toString() })
        // A plan saved before its first date (no declared day): every date from the start counts.
        val fake = FakeSalvavidasPlan(today)
        val body = JsonObject(mapOf("auto_contribution" to JsonObject(mapOf("enabled" to JsonPrimitive(true), "amount" to JsonPrimitive(10000),
            "frequency" to JsonPrimitive("weekly"), "start_date" to JsonPrimitive("2026-10-01")))))
        val (change, refusal) = fake.validate(body, owner = true, balanceKnown = true)
        assertNull(refusal)
        fake.apply(change!!, declaredNow = true)
        // Declared today: nothing counted yet; the next one is a week later.
        val answer = fake.answer(BigDecimal(100000), BigDecimal("3.65"))!!
        assertEquals(0, answer.contributionsCount)
        assertEquals("2026-10-29", answer.nextDate)
        assertEquals(0, BigDecimal(100000).compareTo(answer.total))
    }
}
