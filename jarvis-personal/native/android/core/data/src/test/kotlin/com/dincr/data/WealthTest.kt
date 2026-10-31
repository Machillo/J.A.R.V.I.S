package com.dincr.data

import java.math.BigDecimal
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * WE-2 — Patrimonio: what you have and what you owe, as the backend counts it. An unknown part is
 * named and leaves net worth unknown (never 0). The Swift twin is `WealthTests`. Synthetic data.
 */
class WealthTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false }
    private fun wealth(text: String) = json.decodeFromString<Wealth>(text)
    private val es = AppLanguage.SPANISH

    private val complete = """{"assets":{"accounts":[{"name":"Cuenta","amount":100000,"currency":"CRC","original_amount":100000}],
        "salvavidas":{"name":"Salvavidas","amount":50000},"investments":[{"name":"Fondo","amount":75000}],"total":225000},
        "liabilities":{"debts":[{"name":"Préstamo","amount":200000},{"name":"Tarjeta","amount":100000}],"accounts":[{"name":"Sobregiro","amount":8000}],"total":308000},
        "net_worth":-83000,"complete":true,"unknown":[]}"""

    @Test fun whatYouHaveIsAccountsThenTheSalvavidasThenInvestments() {
        val value = wealth(complete)
        assertEquals(listOf("Cuenta", "Salvavidas", "Fondo"), value.owned.map { it.name })
        assertEquals(0, value.netWorth!!.compareTo(BigDecimal(-83000)))
        assertNull(value.missingNotice(es))
    }

    @Test fun whatYouOweIsOneDebtLineAndEveryOverdraft() {
        val owed = wealth(complete).owed(es)
        assertEquals(listOf("Deudas", "Sobregiro"), owed.map { it.name })
        assertEquals(listOf(0, 0), owed.zip(listOf(300000, 8000)).map { (item, expected) -> item.amount!!.compareTo(BigDecimal(expected)) })
    }

    @Test fun anUnknownPartIsNamedAndTheTotalIsNotGuessed() {
        val value = wealth("""{"assets":{"accounts":[],"salvavidas":{"name":"Salvavidas","amount":null},"investments":[],"total":0},
            "liabilities":{"debts":[{"name":"Préstamo","amount":null}],"accounts":[],"total":0},"net_worth":null,"complete":false,"unknown":["Salvavidas","Préstamo"]}""")
        assertNull(value.netWorth)
        assertNull("an unknown debt is not added as 0", value.owed(es).first().amount)
        assertEquals("Falta el saldo de: Salvavidas, Préstamo. Cuando lo tengamos, te mostramos tu patrimonio neto.", value.missingNotice(es))
    }

    private fun api(plan: PlanTier, role: FakeBackend.Role = FakeBackend.Role.USER) =
        DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(FakeBackend.Scenario.POPULATED, plan, role = role), AppLanguage.SPANISH, backoff = {}))

    @Test fun theFixtureAnswersVipAndTheOwnerAndRefusesTheRest() = runTest {
        for (role in listOf(FakeBackend.Role.USER, FakeBackend.Role.OWNER)) {
            val value = api(PlanTier.VIP, role).wealth()
            assertTrue(value.complete == true && value.netWorth != null)
        }
        for (plan in listOf(PlanTier.FREE, PlanTier.BASIC)) assertTrue(plan.name, runCatching { api(plan).wealth() }.isFailure)
    }
}
