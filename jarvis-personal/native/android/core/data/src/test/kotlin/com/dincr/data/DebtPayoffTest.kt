package com.dincr.data

import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * When the debts are expected to be paid off (the backend's debt_payoff.py estimate per debt).
 * The app never calculates a date: the debt-free month is the latest of the backend's, and only
 * when every unpaid debt has one. iOS: `DebtPayoffTests`. Synthetic data only.
 */
class DebtPayoffTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }
    private fun debts(text: String) = json.decodeFromString(ListSerializer(Debt.serializer()), text)

    @Test fun theEstimateIsReadFromTheDebtsList() {
        val list = debts("""
            [{"id":1,"remaining_amount":100000,"estimated_payoff_months":12,"estimated_payoff_date":"2027-10-05"},
             {"id":2,"remaining_amount":50000,"estimated_payoff_months":null,"estimated_payoff_date":null},
             {"id":3,"remaining_amount":50000}]
        """)
        assertEquals(12, list[0].estimatedPayoffMonths)
        assertEquals("2027-10-05", list[0].estimatedPayoffDate)
        assertNull(list[1].estimatedPayoffMonths)
        assertNull("an older server sends nothing: no date", list[2].estimatedPayoffDate)
    }

    @Test fun theDebtFreeMonthIsTheLatestWhenEveryUnpaidDebtHasOne() {
        val list = debts("""
            [{"id":1,"remaining_amount":100000,"estimated_payoff_date":"2027-10-05"},
             {"id":2,"remaining_amount":20000,"estimated_payoff_date":"2028-03-01"},
             {"id":3,"remaining_amount":0,"estimated_payoff_months":0}]
        """)
        assertEquals(DebtPayoff.Summary("2028-03-01", 0, 2), DebtPayoff.summary(list))
    }

    @Test fun oneUnknownDebtLeavesNoDebtFreeMonthAndIsCounted() {
        val list = debts("""
            [{"id":1,"remaining_amount":100000,"estimated_payoff_date":"2027-10-05"},
             {"id":2,"remaining_amount":20000,"estimated_payoff_date":null}]
        """)
        assertEquals(DebtPayoff.Summary(null, 1, 2), DebtPayoff.summary(list))
    }

    @Test fun withNoUnpaidDebtsThereIsNothingToSay() {
        assertEquals(0, DebtPayoff.summary(debts("""[{"id":1,"remaining_amount":0}]""")).active)
        assertTrue(DebtPayoff.summary(emptyList()).active == 0)
    }

    @Test fun theMonthReadsByNameAndYear() {
        assertEquals("oct 2027", DebtPayoff.monthLabel("2027-10-05", AppLanguage.SPANISH))
        assertEquals("Mar 2028", DebtPayoff.monthLabel("2028-03-01", AppLanguage.ENGLISH))
    }
}
