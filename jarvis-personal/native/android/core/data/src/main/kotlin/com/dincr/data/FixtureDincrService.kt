package com.dincr.data

import java.math.BigDecimal
import java.time.LocalDate
import kotlinx.coroutines.delay
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock

/**
 * In-memory service with synthetic data for previews, UI tests and screenshots. All names and
 * amounts are invented (CLAUDE.md §4.F). Dashboard figures are fixed sample values, exactly as
 * the backend would return them; nothing is computed here. Write semantics follow the backend:
 * a repeated idempotency key adds no second row, and a missing movement is a 404.
 */
class FixtureDincrService(
    private val scenario: Scenario = Scenario.POPULATED,
    private val latencyMs: Long = 350,
    today: LocalDate = LocalDate.now(),
) : DincrService {
    enum class Scenario { POPULATED, EMPTY, FAILING, NEW_USER }

    private val mutex = Mutex()
    private var profile = Profile(
        // Every field /auth/me always sends (auth/saas.py enrich_identity), same as the iOS fixture.
        id = 4201, email = "ana@example.com", displayName = "Ana Solís", role = "user", planSelected = true,
        baseCurrency = "CRC", numberFormat = "dot_comma", currencyPlacement = "before",
        profileSetupCompleted = scenario != Scenario.NEW_USER,
        subscription = Profile.Subscription(plan = "free", status = "active"),
    )
    private val rows = if (scenario == Scenario.POPULATED) sampleMovements(today).toMutableList() else mutableListOf()
    private var nextId = 100
    private val seenKeys = mutableSetOf<String>()

    override suspend fun me(): Profile = pause { profile }

    override suspend fun completeProfileSetup(setup: ProfileSetup): Profile = pause {
        profile = profile.copy(
            displayName = setup.displayName, profileSetupCompleted = true, baseCurrency = setup.baseCurrency,
            numberFormat = setup.numberFormat, currencyPlacement = setup.currencyPlacement,
        )
        profile
    }

    override suspend fun freeDashboard(): FreeDashboard = pause {
        if (scenario == Scenario.EMPTY || scenario == Scenario.NEW_USER) {
            // The backend always returns six months, zero-filled.
            val zero = BigDecimal.ZERO
            FreeDashboard(month = "2026-09", income = zero, expenses = zero, debtPaid = zero, debtBalance = zero, balance = zero, availableAfterCommitments = zero,
                monthlyHistory = listOf("2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09").map { MonthTotals(it, zero, zero, zero, zero) })
        } else SAMPLE_DASHBOARD
    }

    override suspend fun movements(): List<Movement> = pause { rows.sortedByDescending { it.day.orEmpty() } }

    override suspend fun create(kind: MovementKind, entry: EntryCreate, idempotencyKey: String) = pause {
        if (!seenKeys.add(idempotencyKey)) return@pause
        nextId += 1
        val origin = if (kind == MovementKind.INCOME) "salary" else "expense"
        rows += Movement(
            movementId = "$origin:$nextId", sourceId = nextId, origin = origin, transactionDate = entry.entryDate,
            description = entry.description, amount = entry.amount,
            transactionType = if (kind == MovementKind.INCOME) "income" else "expense", category = entry.category, editable = true,
        )
    }

    override suspend fun update(movementId: String, update: MovementUpdate) = pause {
        val index = rows.indexOfFirst { it.movementId == movementId }
        if (index < 0) throw ApiError(ApiError.Kind.NOT_FOUND, 404, message = "Movimiento no encontrado o no editable.")
        rows[index] = rows[index].copy(transactionDate = update.transactionDate, description = update.description, amount = update.amount, category = update.category, notes = update.notes)
    }

    override suspend fun delete(movementId: String) = pause {
        if (!rows.removeAll { it.movementId == movementId }) throw ApiError(ApiError.Kind.NOT_FOUND, 404, message = "Movimiento no encontrado o no eliminable.")
    }

    private suspend fun <T> pause(block: () -> T): T {
        if (latencyMs > 0) delay(latencyMs)
        if (scenario == Scenario.FAILING) {
            throw ApiError(ApiError.Kind.SERVER, 503, message = AppLanguage.current().pick(
                "DINCR no pudo completar la operación. Intentá de nuevo en unos segundos.",
                "DINCR couldn’t complete the operation. Try again in a few seconds."))
        }
        return mutex.withLock { block() }
    }

    companion object {
        private fun m(value: Long) = BigDecimal.valueOf(value)

        val SAMPLE_DASHBOARD = FreeDashboard(
            month = "2026-09", income = m(865_000), expenses = m(512_450), debtPaid = m(95_000), debtBalance = m(1_240_000),
            balance = m(257_550), availableAfterCommitments = m(257_550),
            categories = listOf(
                CategoryAmount("Vivienda", m(210_000)), CategoryAmount("Comida", m(128_300)), CategoryAmount("Transporte", m(64_150)),
                CategoryAmount("Servicios", m(58_000)), CategoryAmount("Entretenimiento", m(32_000)), CategoryAmount("Salud", m(20_000)),
            ),
            monthlyHistory = listOf(
                MonthTotals("2026-04", m(820_000), m(598_000), m(95_000), m(127_000)),
                MonthTotals("2026-05", m(820_000), m(541_200), m(95_000), m(183_800)),
                MonthTotals("2026-06", m(905_000), m(630_500), m(95_000), m(179_500)),
                MonthTotals("2026-07", m(840_000), m(575_900), m(95_000), m(169_100)),
                MonthTotals("2026-08", m(865_000), m(603_300), m(95_000), m(166_700)),
                MonthTotals("2026-09", m(865_000), m(512_450), m(95_000), m(257_550)),
            ),
        )

        fun sampleMovements(today: LocalDate): List<Movement> {
            fun day(offset: Long) = today.minusDays(offset).toString()
            fun row(id: String, offset: Long, text: String, amount: BigDecimal, type: String, category: String, editable: Boolean = true) =
                Movement(movementId = id, sourceId = id.substringAfter(':').toInt(), origin = id.substringBefore(':'), transactionDate = day(offset),
                    description = text, amount = amount, transactionType = type, category = category, editable = editable)
            fun row(id: String, offset: Long, text: String, amount: Long, type: String, category: String, editable: Boolean = true) =
                row(id, offset, text, m(amount), type, category, editable)
            return listOf(
                row("expense:11", 0, "Supermercado", 18_450, "expense", "Comida"),
                row("expense:10", 0, "Café", 2_300, "expense", "Restaurante"),
                // Cents and a category outside the editor's list: editing must keep both.
                row("expense:12", 1, "Feria del agricultor", BigDecimal("12345.5"), "expense", "Feria"),
                row("transaction:9", 1, "Aviso bancario · Gasolinera", 25_000, "expense", "Gasolina", editable = false),
                row("salary:8", 3, "Salario quincenal", 432_500, "income", "Salario"),
                row("expense:7", 4, "Internet del hogar", 24_900, "expense", "Internet"),
                row("expense:6", 6, "Farmacia", 9_800, "expense", "Salud"),
                row("expense:5", 9, "Alquiler", 210_000, "expense", "Vivienda"),
                row("salary:4", 18, "Salario quincenal", 432_500, "income", "Salario"),
            )
        }
    }
}
