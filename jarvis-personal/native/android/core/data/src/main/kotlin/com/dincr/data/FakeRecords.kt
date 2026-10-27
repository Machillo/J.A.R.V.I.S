package com.dincr.data

import java.math.BigDecimal
import java.time.LocalDate

/**
 * The fake backend's JARVIS → Registros (fixtures only). Same shapes as FastAPI's
 * `/finance/timeline` and `/finance/reconciliation` (Owner routes; [FakeBackend] refuses everyone
 * else). Invented accounts and amounts. iOS: FixtureBackend+Records.swift.
 */
internal class FakeRecords(private val today: LocalDate) {
    private val confirmed = mutableMapOf<Long, BigDecimal>()

    fun timeline(): MoneyTimeline {
        var balance = BigDecimal(310_000)
        val events = listOf(
            Triple(3L, "Cuota · Préstamo de ejemplo", "debt_payment" to BigDecimal(-50_000)),
            Triple(8L, "Internet de ejemplo", "recurring_expense" to BigDecimal(-24_900)),
            Triple(12L, "Ingreso de salario", "income" to BigDecimal(450_000)),
        ).map { (days, name, kindImpact) ->
            balance += kindImpact.second
            MoneyTimeline.Event(today.plusDays(days).toString(), name, kindImpact.first, kindImpact.second.abs(), kindImpact.second, balance)
        }
        return MoneyTimeline(today.toString(), today.plusDays(45).toString(), BigDecimal(310_000), balance, events,
            listOf("Solo se proyectan ingresos con calendario configurado y obligaciones activas con fecha y monto."))
    }

    fun reconciliation(): Reconciliation {
        fun account(id: Long, name: String, last4: String, expected: BigDecimal, real: BigDecimal): Reconciliation.Account {
            val confirmedBalance = confirmed[id]
            val realBalance = confirmedBalance ?: real
            val expectedBalance = confirmedBalance ?: expected
            val difference = realBalance - expectedBalance
            return Reconciliation.Account(id, name, "Banco de ejemplo", last4, "CRC", expectedBalance, realBalance, difference,
                if (confirmedBalance == null) 4 else 0, today.minusDays(6).toString(), if (difference.signum() == 0) "ok" else "needs_review")
        }
        val accounts = listOf(account(801, "Cuenta de ejemplo", "1111", BigDecimal(290_000), BigDecimal(310_000)),
            account(802, "Ahorro de ejemplo", "2222", BigDecimal(120_000), BigDecimal(120_000)))
        return Reconciliation(accounts, Reconciliation.Summary(accounts.size, accounts.count { it.needsReview }, 2, 0, 1),
            "DINCR solo detecta y propone revisión. Ningún movimiento se borra, duplica o corrige automáticamente.")
    }

    /** Null when the account is unknown (the backend answers 404). */
    fun confirm(id: Long?, balance: BigDecimal?): ReconciliationConfirmResult? {
        if (id !in setOf(801L, 802L) || balance == null) return null
        confirmed[id!!] = balance
        return ReconciliationConfirmResult("OK", true)
    }
}
