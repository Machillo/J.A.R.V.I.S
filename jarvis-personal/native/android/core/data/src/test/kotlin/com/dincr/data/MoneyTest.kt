package com.dincr.data

import java.math.BigDecimal
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * JARVIS → Mi dinero (Owner): the cycle report and the accounts as the app reads them, and the
 * account request. Unknown amounts stay null (never 0). iOS: `MoneyTests`. Synthetic data only.
 */
class MoneyTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }

    private fun same(expected: Int, actual: BigDecimal?) = assertEquals(0, BigDecimal(expected).compareTo(actual))

    @Test fun theCycleReportReadsTheFiguresTheScreenShows() {
        val report = json.decodeFromString(CycleReport.serializer(), """
            {"status":"OK","as_of":"2026-10-25","cycle":{"start":"2026-10-05","end":"2026-11-04","label":"x","closing_day":5},
             "expense_cycle":{"start":"2026-09-21","end":"2026-10-20","closed":true},
             "income":{"fixed_expected":900000,"extra_expected":0,"expected_total":900000,"received_from_transactions":450000,
                       "pending_projection":450000,"other_cash_inflows":0,"items":[]},
             "expenses":{"current_period":380000,"spending_only":260000,"debt_payments":120000,"transaction_count":18,"items":[]},
             "goals":{"reserved_current_period":50000},"cashflow":{"real_balance":470000,"loan_received":0,"formula":"x"},"user_id":1}
        """)
        assertEquals("2026-10-05", report.cycle?.start)
        assertEquals(true, report.expenseCycle?.closed)
        same(900_000, report.income?.expectedTotal)
        same(450_000, report.income?.receivedFromTransactions)
        same(450_000, report.income?.pendingProjection)
        same(260_000, report.expenses?.spendingOnly)
        same(120_000, report.expenses?.debtPayments)
        same(50_000, report.goals?.reservedCurrentPeriod)
        same(470_000, report.cashflow?.realBalance)
    }

    @Test fun aMissingFigureIsUnknownNotZero() {
        val report = json.decodeFromString(CycleReport.serializer(), """{"status":"OK","income":{"expected_total":null},"expenses":{}}""")
        assertNull(report.income?.expectedTotal)
        assertNull(report.income?.receivedFromTransactions)
        assertNull(report.expenses?.spendingOnly)
        assertNull(report.cashflow)
        assertNull(report.cycle)
    }

    @Test fun theAccountsReadEachBalanceAndWhichCanBeEdited() {
        val balances = json.decodeFromString(AccountBalances.serializer(), """
            {"status":"OK","total_real_balance":910000,"currency":"CRC","items":[
              {"id":901,"account_name":"Cuenta","bank_name":"Banco","account_last4":"1111","currency":"CRC","account_type":"checking",
               "current_balance":300000,"calculated_balance":310000,"balance_crc":310000,"balance_as_of":"2026-10-22T10:00:00",
               "include_in_net_worth":true,"source":"manual","movements_since_balance":2},
              {"id":903,"account_name":"Detectada","account_last4":"","current_balance":0,"include_in_net_worth":false},
              {"id":"ibkr-7","account_name":"Inversiones","currency":"USD","current_balance":1500,"read_only":true}]}
        """)
        same(910_000, balances.totalRealBalance)
        assertEquals(listOf("901", "903", "ibkr-7"), balances.items.map { it.id })
        val first = balances.items[0]
        same(310_000, first.balance)
        assertEquals("1111", first.accountLast4)
        assertEquals(901L, first.accountId)
        assertTrue(first.isEditable)
        assertNull(balances.items[1].accountLast4)
        assertFalse(balances.items[1].includeInNetWorth)
        same(0, balances.items[1].balance)
        assertNull(balances.items[2].accountId)
        assertFalse(balances.items[2].isEditable)
        same(1_500, balances.items[2].balance)
    }

    @Test fun anAccountWithoutBalanceIsUnknownNotZero() {
        val balances = json.decodeFromString(AccountBalances.serializer(), """{"status":"OK","items":[{"id":5,"account_name":"Sin saldo"}]}""")
        assertNull(balances.totalRealBalance)
        assertNull(balances.items[0].balance)
    }

    @Test fun theSaveSendsTheBackendsFieldNames() {
        val body = json.encodeToString(AccountBalanceRequest.serializer(),
            AccountBalanceRequest("Cuenta", BigDecimal(50_000), "Banco", "4444", "USD", "savings", includeInNetWorth = false))
        listOf("\"account_name\":\"Cuenta\"", "\"current_balance\":50000", "\"bank_name\":\"Banco\"", "\"account_last4\":\"4444\"", "\"currency\":\"USD\"",
            "\"account_type\":\"savings\"", "\"include_in_net_worth\":false", "\"annual_interest_rate\":0", "\"source\":\"manual\"", "\"note\":\"\"")
            .forEach { assertTrue("$it in $body", body.contains(it)) }
    }

    @Test fun theLastDigitsAreFourNumbersOrNothing() {
        assertTrue(AccountBalanceRequest.isValidLast4("") && AccountBalanceRequest.isValidLast4("0123"))
        assertFalse(AccountBalanceRequest.isValidLast4("123") || AccountBalanceRequest.isValidLast4("12a4") || AccountBalanceRequest.isValidLast4("12345"))
    }

    @Test fun moneyIsAnAvailableJarvisSection() {
        assertTrue(Jarvis.Section.MONEY.isAvailable)
    }
}
