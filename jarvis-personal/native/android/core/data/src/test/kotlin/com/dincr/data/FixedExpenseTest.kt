package com.dincr.data

import java.math.BigDecimal
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Plan → Gastos fijos (FX-1): the Owner's `/finance/fixed-expenses` rows decode, the request sends only
 * what the form edits (monthly, every N months), the form's checks, and the fake keeps the backend's
 * access rule and "remove = deactivate". Synthetic figures only. iOS: `FixedExpenseTests.swift`.
 */
class FixedExpenseTest {
    private val json = Json { ignoreUnknownKeys = true; explicitNulls = false; encodeDefaults = true }

    private fun api(role: FakeBackend.Role) =
        DincrApi(ApiClient("https://fixtures.invalid", { "t" }, FakeBackend(FakeBackend.Scenario.POPULATED, PlanTier.VIP, role = role), AppLanguage.SPANISH, backoff = {}))

    @Test fun rowsDecodeAndCostPerMonth() {
        val rows = json.decodeFromString<List<OwnerFixedExpense>>(
            """[{"id":1,"name":"Internet de ejemplo","expected_amount":24900.0,"interval_months":1,"due_day":8,"is_active":true,"aliases":[]},
                {"id":2,"name":"Seguro de ejemplo","expected_amount":60000,"interval_months":2,"due_day":null}]""")
        assertEquals(listOf(1L, 2L), rows.map { it.id })
        assertEquals(0, BigDecimal(30_000).compareTo(rows[1].monthlyAmount))
        assertNull(rows[1].dueDay)
    }

    @Test fun theRequestSendsOnlyWhatTheFormEdits() {
        val body = json.parseToJsonElement(json.encodeToString(OwnerFixedExpenseRequest.serializer(),
            OwnerFixedExpenseRequest("Gimnasio de ejemplo", "Salud", BigDecimal("25000.50"), 1))).jsonObject
        assertEquals(setOf("name", "category", "expected_amount", "interval_months", "frequency"), body.keys)
        assertEquals("\"monthly\"", body["frequency"].toString())
    }

    @Test fun theFormRefusesWhatTheBackendWouldStoreWrong() {
        assertEquals("Escribí un nombre.", OwnerFixedExpenseRequest.problem(" ", BigDecimal.ONE, 1, null))
        assertTrue(OwnerFixedExpenseRequest.problem("A", BigDecimal.ZERO, 1, null) != null)
        assertTrue(OwnerFixedExpenseRequest.problem("A", BigDecimal.ONE, 5, null) != null)
        assertEquals("El día va de 1 a 31.", OwnerFixedExpenseRequest.problem("A", BigDecimal.ONE, 1, 32))
        assertNull(OwnerFixedExpenseRequest.problem("A", BigDecimal.ONE, 12, 31))
    }

    @Test fun theFakeIsTheOwnersAloneAndRemovingDeactivates() = runBlocking {
        assertThrows(ApiError::class.java) { runBlocking { api(FakeBackend.Role.USER).ownerFixedExpenses() } }
        val owner = api(FakeBackend.Role.OWNER)
        val before = owner.ownerFixedExpenses()
        val first = before.first()
        owner.removeOwnerFixedExpense(first.id)
        owner.createOwnerFixedExpense(OwnerFixedExpenseRequest("Agua de ejemplo", "Servicios", BigDecimal(9_000), 1, 3))
        val after = owner.ownerFixedExpenses()
        assertFalse(after.any { it.id == first.id })
        assertTrue(after.any { it.name == "Agua de ejemplo" && it.dueDay == 3 && it.expectedAmount?.compareTo(BigDecimal(9_000)) == 0 })
        assertEquals(before.size, after.size)
    }
}
