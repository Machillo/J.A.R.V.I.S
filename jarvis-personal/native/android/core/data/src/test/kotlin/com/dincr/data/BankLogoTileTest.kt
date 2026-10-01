package com.dincr.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * The historical MultiMoney logo is white on transparent: it sits on the historical dark tile, every
 * other logo on white. iOS twin: `PlanAccountsTests.theWhiteMultiMoneyLogoSitsOnTheHistoricalDarkTile`.
 */
class BankLogoTileTest {
    @Test fun theWhiteMultiMoneyLogoSitsOnTheHistoricalDarkTile() {
        assertTrue(BankBranding.identify("multimoney")!!.logoNeedsDarkTile)
        listOf("bac", "bcr", "bn", "popular", "promerica", "davivienda", "davibank").forEach {
            assertEquals(it, false, BankBranding.identify(it)!!.logoNeedsDarkTile)
        }
        assertTrue(BankBranding.identify("cooperativa ejemplo")?.logoNeedsDarkTile != true)
    }
}
