package com.dincr.data

import java.math.BigDecimal
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * A debt's unknown interest rate is not 0% (debts.interest_rate_known): the edit form starts an
 * unknown rate empty, an edit confirms the rate only when the user touched it, and VIP asks for the
 * missing rates (`debt_interest_rates`) instead of naming a debt. The Swift twin is
 * `DebtInterestRateTests`. Synthetic data.
 */
class DebtInterestRateTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = false }
    private fun debt(raw: String) = json.decodeFromString<Debt>(raw)

    @Test fun anUnknownRateStartsEmptyNeverZero() {
        assertNull(debt("""{"id":1,"remaining_amount":1000,"interest_rate":0,"interest_rate_known":false}""").rateForEditing)
        assertEquals(0, debt("""{"id":1,"remaining_amount":1000,"interest_rate":0,"interest_rate_known":true}""").rateForEditing?.compareTo(BigDecimal.ZERO))
        assertEquals(0, debt("""{"id":1,"remaining_amount":1000,"interest_rate":24,"interest_rate_known":true}""").rateForEditing?.compareTo(BigDecimal(24)))
        // An older server (no flag): the stored rate as before.
        assertEquals(0, debt("""{"id":1,"remaining_amount":1000,"interest_rate":18}""").rateForEditing?.compareTo(BigDecimal(18)))
    }

    @Test fun anEditConfirmsTheRateOnlyWhenTheUserTouchedIt() {
        assertFalse(DebtRequest.rateConfirmed("", ""))
        assertFalse(DebtRequest.rateConfirmed("24", " 24 "))
        assertTrue(DebtRequest.rateConfirmed("", "0"))       // an unknown rate typed as 0%
        assertTrue(DebtRequest.rateConfirmed("24", "21"))
        assertTrue(DebtRequest.rateConfirmed("24", ""))      // cleared
    }

    @Test fun theConfirmationIsSentOnlyWhenSet() {
        val edit = json.encodeToString(DebtRequest("Tarjeta", remainingAmount = BigDecimal(1000), interestRate = BigDecimal.ZERO, interestRateConfirmed = true))
        assertTrue(edit.contains("\"interest_rate_confirmed\":true") && edit.contains("\"interest_rate\":"))
        val create = json.encodeToString(DebtRequest("Tarjeta", remainingAmount = BigDecimal(1000)))
        assertFalse(create.contains("interest_rate"))  // no rate: unknown
    }

    @Test fun vipAsksForTheMissingRatesInsteadOfNamingADebt() {
        val center = json.decodeFromString<CommandCenter>("""{"safe_to_spend":{"amount":118000,"monthly_margin":214000,"next_45_days_minimum":96000,"missing":[]},
            "director":{"priority":"debt","headline":"Completá las tasas de interés para saber qué deuda atacar primero","missing":["debt_interest_rates"]},
            "alerts":[]}""")
        val home = HomeToday.vip(center, null, null, emptyList())
        assertEquals(0, home.status.amount?.compareTo(BigDecimal(118000)))  // safe to spend doesn't use rates
        assertEquals(HomeNext.Kind.NEEDS_INFORMATION, home.next.kind)
        assertEquals(listOf(HomeInput.DEBT_INTEREST_RATES), home.next.missing)
        assertEquals(HomeDestination.DEBTS, home.next.destination)
        assertEquals(HomeDestination.DEBTS, HomeInput.DEBT_INTEREST_RATES.destination)
    }

    @Test fun theVipPlanCarriesBasicsWarningAndTheMissingCode() {
        val plan = json.decodeFromString<DirectorStrategy>(
            """{"scope":"users","warnings":["Falta la tasa de interés de 1 deuda; la prioridad usa los datos disponibles."],"missing":["debt_interest_rates"]}""")
        assertTrue(plan.warnings.first().startsWith("Falta la tasa de interés"))
        assertTrue(plan.needsDebtRates)
        assertFalse(json.decodeFromString<DirectorStrategy>("""{"scope":"users","warnings":[],"missing":[]}""").needsDebtRates)
    }
}
