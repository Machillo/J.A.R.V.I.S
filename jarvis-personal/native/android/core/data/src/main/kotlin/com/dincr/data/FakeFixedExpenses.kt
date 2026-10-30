package com.dincr.data

import java.math.BigDecimal

/**
 * The fake backend's Plan → Gastos fijos for the Owner (fixtures only). Same shapes as FastAPI's
 * `/finance/fixed-expenses` (an Owner route; [FakeBackend] refuses everyone else): a POST with an
 * existing name updates that row, DELETE deactivates. Invented names and amounts.
 * iOS: FixtureBackend+FixedExpenses.swift.
 */
internal class FakeFixedExpenses(private val nextId: () -> Long) {
    private val rows = mutableListOf(
        OwnerFixedExpense(9101, "Internet de ejemplo", "Servicios", BigDecimal(24_900), "CRC", "monthly", 1, 8, true),
        OwnerFixedExpense(9102, "Gimnasio de ejemplo", "Salud", BigDecimal(30_000), "CRC", "monthly", 1, 15, true),
        OwnerFixedExpense(9103, "Seguro de ejemplo", "Seguros", BigDecimal(60_000), "CRC", "monthly", 2, null, true),
    )

    fun list(): List<OwnerFixedExpense> = rows.filter { it.isActive == true }.sortedWith(compareBy({ it.dueDay ?: 99 }, { it.name }))

    fun create(name: String?, category: String?, amount: BigDecimal?, interval: Int?, dueDay: Int?): OwnerFixedExpense? {
        val clean = name?.trim().orEmpty().ifEmpty { return null }
        val id = rows.firstOrNull { it.name == clean }?.id ?: nextId()
        rows.removeAll { it.id == id }
        val row = OwnerFixedExpense(id, clean, category ?: "Gastos fijos", amount, "CRC", "monthly", interval ?: 1, dueDay, true)
        rows += row
        return row
    }

    fun update(id: Long?, name: String?, category: String?, amount: BigDecimal?, interval: Int?, dueDay: Int?): OwnerFixedExpense? {
        val index = rows.indexOfFirst { it.id == id }.takeIf { it >= 0 } ?: return null
        val old = rows[index]
        rows[index] = old.copy(name = name ?: old.name, category = category ?: old.category, expectedAmount = amount ?: old.expectedAmount,
            intervalMonths = interval ?: old.intervalMonths, dueDay = dueDay ?: old.dueDay)
        return rows[index]
    }

    fun deactivate(id: Long?): OwnerFixedExpense? {
        val index = rows.indexOfFirst { it.id == id }.takeIf { it >= 0 } ?: return null
        rows[index] = rows[index].copy(isActive = false)
        return rows[index]
    }
}
