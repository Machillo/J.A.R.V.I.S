package com.dincr.data

import java.math.BigDecimal
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * JARVIS → Patrimonio (Owner): the investment and business centers as the app reads them, and the
 * write requests. Without a portfolio snapshot the backend's 0 figures are unknown, never shown.
 * iOS: `WealthCenterTests`. Synthetic data only.
 */
class WealthCenterTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }

    private fun same(expected: Int, actual: BigDecimal?) = assertEquals(0, BigDecimal(expected).compareTo(actual))

    @Test fun theInvestmentCenterReadsThePortfolioAndItsPositions() {
        val center = json.decodeFromString(InvestmentCenter.serializer(), """
            {"portfolio":{"id":1,"market_value":1500,"contributed_capital":1350,"realized_pnl":0,"unrealized_pnl":130,"dividends":20,
                          "currency":"USD","source":"ibkr_readonly","snapshot_at":"2026-10-20T12:00:00+00:00"},
             "flows":[],"reserved_to_invest_crc":100000,"gross_pnl":150,"net_pnl":150,"return_pct":11.11,
             "positions":[{"symbol":"ETF A","sec_type":"ETF","currency":"USD","position":10,"market_price":100,"market_value":1000,"unrealized_pnl":100},
                          {"symbol":"Acción B","sec_type":"STK","currency":"USD","position":5,"market_value":500,"unrealized_pnl":30}],
             "sync_status":"current","snapshot_age_seconds":18000,"read_only":true,"sync_method":"flex","flex_configured":true,"included_in_net_worth":true}
        """)
        assertTrue(center.hasPortfolio)
        val figures = assertNotNullAnd(center.figures)
        same(1_500, figures.marketValue)
        same(1_350, figures.contributedCapital)
        same(150, figures.netPnl)
        assertEquals(0, BigDecimal("11.11").compareTo(figures.returnPct))
        assertEquals("USD", figures.currency)
        assertEquals(listOf("ETF A", "Acción B"), center.positions.map { it.symbol })
        same(10, center.positions[0].quantity)
        assertNull(center.positions[1].marketPrice)
        same(100_000, center.reservedToInvestCrc)
        assertEquals(InvestmentCenter.SyncState.CURRENT, center.syncState)
        assertEquals(5L, center.ageHours)
        assertTrue(center.flexConfigured)
    }

    @Test fun noSnapshotIsUnknownNotZero() {
        // The backend still answers 0 gains and 0 % when there is no snapshot.
        val center = json.decodeFromString(InvestmentCenter.serializer(), """
            {"portfolio":{},"flows":[],"reserved_to_invest_crc":0,"gross_pnl":0,"net_pnl":0,"return_pct":0,"positions":[],
             "sync_status":"manual_ready_for_ibkr","snapshot_age_seconds":null,"read_only":false,"sync_method":"manual","flex_configured":false}
        """)
        assertFalse(center.hasPortfolio)
        assertNull(center.figures)
        assertEquals(InvestmentCenter.SyncState.MANUAL, center.syncState)
        assertNull(center.ageHours)
        assertFalse(center.flexConfigured)
    }

    @Test fun noContributedCapitalLeavesTheReturnUnknown() {
        val center = json.decodeFromString(InvestmentCenter.serializer(), """{"portfolio":{"market_value":200,"contributed_capital":0},"net_pnl":0,"return_pct":0}""")
        assertTrue(center.hasPortfolio)
        same(200, center.figures?.marketValue)
        assertNull(center.figures?.returnPct)
        // IBKR never sends it and the column defaults to 0: that is unknown, not "you put in $0".
        assertNull(center.figures?.contributedCapital)
    }

    @Test fun theRateTheNetWorthUsesIsReadWithItsDate() {
        val center = json.decodeFromString(InvestmentCenter.serializer(), """{"portfolio":{"market_value":200},"net_worth_rate":{"rate":500,"date":"2026-08-16"}}""")
        same(500, center.netWorthRate?.rate)
        assertEquals("2026-08-16", center.netWorthRate?.date)
        assertNull(json.decodeFromString(InvestmentCenter.serializer(), """{"portfolio":{},"net_worth_rate":null}""").netWorthRate)
    }

    @Test fun theBusinessCenterReadsTheBusinessesTheirMovementsAndTotals() {
        val center = json.decodeFromString(BusinessCenter.serializer(), """
            {"businesses":[{"id":1,"name":"Negocio A","description":"Algo","ownership_pct":100,"status":"active"},{"id":2,"name":"Negocio B","ownership_pct":50}],
             "movements":[{"id":11,"business_id":1,"movement_date":"2026-10-12","movement_type":"income","amount":80000,"description":"Venta"},
                          {"id":12,"business_id":1,"movement_date":"2026-10-05","movement_type":"expense","amount":30000,"description":"Insumos"}],
             "income":80000,"expenses":30000,"profit":50000,"capital":0}
        """)
        assertEquals(listOf(1L, 2L), center.businesses.map { it.id })
        same(50, center.businesses[1].ownershipPct)
        assertEquals(listOf(11L, 12L), center.movementsOf(center.businesses[0]).map { it.id })
        assertTrue(center.movementsOf(center.businesses[1]).isEmpty())
        same(80_000, center.income)
        same(30_000, center.expenses)
        same(50_000, center.profit)
        same(0, center.capital)
    }

    @Test fun anEmptyBusinessCenterHasNoTotals() {
        val center = json.decodeFromString(BusinessCenter.serializer(), "{}")
        assertTrue(center.businesses.isEmpty())
        assertNull(center.income)
        assertNull(center.profit)
    }

    @Test fun theWritesSendTheBackendsFieldNames() {
        assertEquals("""{"name":"Negocio nuevo","description":"Detalle","ownership_pct":60}""",
            json.encodeToString(BusinessCreateRequest.serializer(), BusinessCreateRequest("Negocio nuevo", "Detalle", BigDecimal(60))))
        assertEquals("""{"name":"Solo nombre","ownership_pct":100}""", json.encodeToString(BusinessCreateRequest.serializer(), BusinessCreateRequest("Solo nombre")))
        val movement = BusinessMovementRequest(1, "expense", BigDecimal(12_500), "2026-10-20", "Insumos")
        assertEquals("""{"business_id":1,"movement_type":"expense","amount":12500,"movement_date":"2026-10-20","description":"Insumos"}""",
            json.encodeToString(BusinessMovementRequest.serializer(), movement))
        assertTrue(movement.createsTransaction)
        assertFalse(BusinessMovementRequest(1, "capital", BigDecimal.ONE, description = "Aporte").createsTransaction)
    }

    @Test fun wealthIsAnAvailableJarvisSection() {
        assertTrue(Jarvis.Section.WEALTH.isAvailable)
    }

    private fun <T> assertNotNullAnd(value: T?): T {
        assertNotNull(value)
        return value!!
    }

    @Test fun theDividendPlanKeepsUnknownFiguresUnknown() {
        val plan = json.decodeFromString(DividendPlan.serializer(), """
            {"config":{"stocks":[],"goal_monthly_usd":1000,"monthly_amount_usd":null,"withholding_pct":30},"held_symbols":["AAA"],
             "gate":{"open":false,"blockers":[{"code":"salvavidas_unknown"}]},
             "result":{"ready":false,"capital_needed_usd":null,"current_value_usd":null,"months_to_goal":null,"monthly_needed":[],"buy_this_month":[]}}
        """)
        assertFalse(plan.isConfigured)
        assertEquals(listOf("salvavidas_unknown"), plan.gate.blockers.map { it.code })
        assertNull(plan.result.currentValueUsd)
        assertNull(plan.result.capitalNeededUsd)
        assertNull(plan.result.monthsToGoal)
    }

    @Test fun aReadyDividendPlanReadsItsFigures() {
        val plan = json.decodeFromString(DividendPlan.serializer(), """
            {"config":{"stocks":[{"symbol":"AAA","share_pct":100,"yield_pct":4}],"goal_monthly_usd":1000,"monthly_amount_usd":200,"withholding_pct":30},"held_symbols":[],
             "gate":{"open":true,"blockers":[]},
             "result":{"ready":true,"net_yield_pct":2.8,"capital_needed_usd":1000,"current_value_usd":0,"missing_usd":1000,"months_to_goal":5,
                       "monthly_needed":[{"years":10,"amount_usd":7}],"buy_this_month":[{"symbol":"AAA","amount_usd":200}]}}
        """)
        assertTrue(plan.isConfigured && plan.result.ready)
        same(0, plan.result.currentValueUsd)
        assertEquals(5, plan.result.monthsToGoal)
        assertEquals(10, plan.result.monthlyNeeded.first().years)
        same(200, plan.result.buyThisMonth.first().amountUsd)
    }

    @Test fun aDividendPlanSaveSendsEveryFieldSoANullClearsIt() {
        val sent = Json { explicitNulls = true }.encodeToString(DividendPlanUpdate.serializer(), DividendPlanUpdate(listOf(DividendPlan.Stock("AAA", BigDecimal(100)))))
        assertTrue(sent, sent.contains("\"monthly_amount_usd\":null") && sent.contains("\"goal_monthly_usd\":null") && sent.contains("\"yield_pct\":null"))
    }
}
