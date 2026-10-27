package com.dincr.data

import java.math.BigDecimal

/**
 * The fake backend's JARVIS → Control de dinero (fixtures only). Same shapes as FastAPI's
 * `/finance/receivables*` (an Owner route; [FakeBackend] refuses everyone else). A write the backend
 * refuses answers 200 with `status` ≠ "OK", as the real one does. Invented names and amounts.
 * iOS: FixtureBackend+Receivables.swift.
 */
internal class FakeReceivables(private val today: java.time.LocalDate, private val nextId: () -> Long) {
    private data class Entry(val id: Long, val type: String, val amount: BigDecimal, val description: String, val date: String, val source: String)
    private data class Person(val id: Long, val name: String, val carried: BigDecimal, val entries: MutableList<Entry>) {
        val charges get() = entries.filter { it.type == "charge" }.fold(BigDecimal.ZERO) { sum, e -> sum + e.amount }
        val payments get() = entries.filter { it.type == "payment" }.fold(BigDecimal.ZERO) { sum, e -> sum + e.amount }
        val due get() = carried + charges - payments
        val status get() = when {
            due.signum() < 0 -> "credit"
            due.signum() == 0 -> "completed"
            payments.signum() > 0 -> "partial"
            else -> "pending"
        }
    }

    private val people = mutableListOf(
        Person(7001, "Ana de ejemplo", BigDecimal.ZERO, mutableListOf(Entry(7101, "charge", BigDecimal(35_000), "Cena compartida", "2026-10-02", "manual_purchase"))),
        Person(7002, "Luis de ejemplo", BigDecimal(20_000), mutableListOf(
            Entry(7102, "charge", BigDecimal(15_000), "Compra con tarjeta adicional", "2026-10-04", "additional_card_auto"),
            Entry(7103, "payment", BigDecimal(10_000), "Pago en efectivo", "2026-10-10", "cash_collection"))),
    )

    fun report(): ReceivablesReport {
        val open = people.filter { it.due.signum() > 0 }
        return ReceivablesReport(
            cycle = ReceivablesReport.Cycle("2026-09-21", "2026-10-21"),
            items = people.map { p ->
                Receivable(p.id, p.name, p.due, p.carried, p.charges, p.payments, p.status, p.entries.any { it.source == "additional_card_auto" },
                    p.entries.map { ReceivableEntry(it.id, it.type, it.amount, it.description, it.date, it.source) })
            },
            summary = ReceivablesReport.Summary(open.fold(BigDecimal.ZERO) { sum, p -> sum + p.due }, open.size, people.size),
        )
    }

    fun addEntry(personName: String?, amount: BigDecimal?, description: String?, kind: String?): ReceivableWriteResult {
        val name = personName?.trim().orEmpty()
        if (name.isEmpty() || amount == null || amount.signum() <= 0) return ReceivableWriteResult("ERROR", "Persona y monto mayor a cero requeridos.")
        val entry = Entry(nextId(), "charge", amount, description.orEmpty(), today.toString(), "manual_${kind ?: "purchase"}")
        val person = people.firstOrNull { it.name.equals(name, ignoreCase = true) }
        if (person != null) person.entries.add(0, entry) else people += Person(nextId(), name, BigDecimal.ZERO, mutableListOf(entry))
        return ReceivableWriteResult("OK")
    }

    fun pay(id: Long?, amount: BigDecimal?, notes: String?, date: String?): ReceivableWriteResult {
        val person = people.firstOrNull { it.id == id } ?: return ReceivableWriteResult("NOT_FOUND", "Cuenta por cobrar no encontrada.")
        if (amount == null || amount.signum() <= 0) return ReceivableWriteResult("ERROR", "Monto inválido.")
        person.entries.add(0, Entry(nextId(), "payment", amount, notes.orEmpty(), date ?: today.toString(), "cash_collection"))
        return ReceivableWriteResult("OK")
    }
}
