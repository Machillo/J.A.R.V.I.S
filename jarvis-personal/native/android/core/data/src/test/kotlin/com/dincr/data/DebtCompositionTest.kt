package com.dincr.data

import java.math.BigDecimal
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * §15 PR 8 — the debt composition in Patrimonio reads Plan → Deudas' balances as they are: active
 * debts only, an unknown balance never drawn as 0. The Swift twin is `DebtCompositionTests`. Synthetic data.
 */
class DebtCompositionTest {
    private fun debt(id: Long, name: String, remaining: Long?) = Debt(id, name, remainingAmount = remaining?.let { BigDecimal(it) })

    @Test fun activeDebtsMakeUpWhatIsOwedInTheirOrder() {
        val composition = DebtComposition.of(listOf(debt(1, "Tarjeta", 480_000), debt(2, "Préstamo", 520_000)))
        assertEquals(Composition.Status.COMPLETE, composition.status)
        assertEquals(listOf("Tarjeta", "Préstamo"), composition.segments.map { it.label })
        assertEquals(listOf(48L, 52L), composition.segments.map { Math.round((it.share ?: -1.0) * 100) })
        assertEquals(0, composition.total?.compareTo(BigDecimal(1_000_000)))
    }

    @Test fun aPaidDebtIsNotPartOfIt() {
        assertEquals(listOf("Tarjeta"), DebtComposition.of(listOf(debt(1, "Tarjeta", 300_000), debt(2, "Pagada", 0))).segments.map { it.label })
    }

    @Test fun anUnknownBalanceIsNeverZeroAndBlocksSharesAndTotal() {
        val composition = DebtComposition.of(listOf(debt(1, "Tarjeta", 300_000), debt(2, "Sin saldo", null)))
        assertEquals(Composition.Status.PARTIAL, composition.status)
        assertNull(composition.total)
        assertTrue(composition.segments.all { it.share == null })
        assertEquals(listOf("Sin saldo"), composition.unknown.map { it.label })
    }

    @Test fun noActiveDebtIsAnEmptyComposition() {
        assertEquals(Composition.Status.EMPTY, DebtComposition.of(emptyList()).status)
        assertEquals(Composition.Status.EMPTY, DebtComposition.of(listOf(debt(1, "Pagada", 0))).status)
    }

    @Test fun theFixtureDebtsAreDrawable() = runTest {
        val api = DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(FakeBackend.Scenario.POPULATED, PlanTier.FREE), AppLanguage.SPANISH, backoff = {}))
        val debts = api.debts()
        assertTrue(debts.isNotEmpty())
        assertEquals(Composition.Status.COMPLETE, DebtComposition.of(debts).status)
    }
}
