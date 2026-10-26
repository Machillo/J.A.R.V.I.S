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
}
