package com.dincr.data

import java.math.BigDecimal

/**
 * The fake backend's JARVIS → Patrimonio (fixtures only). Same shapes as FastAPI's
 * `/finance/investment-center*` and `/finance/business-center*` (Owner routes; [FakeBackend] refuses
 * everyone else). Invented names and amounts. iOS: FixtureBackend+Wealth.swift.
 */
internal class FakeWealth(private val today: java.time.LocalDate, private val nextId: () -> Long) {
    private val businesses = mutableListOf(BusinessCenter.Business(9101, "Negocio de ejemplo", "Venta de ejemplo", BigDecimal(100), "active"))
    private val movements = mutableListOf(
        BusinessCenter.Movement(9201, 9101, "2026-10-12", "income", BigDecimal(80_000), "Venta de ejemplo"),
        BusinessCenter.Movement(9202, 9101, "2026-10-05", "expense", BigDecimal(30_000), "Insumos de ejemplo"),
    )
    /** Seconds since the snapshot: a few hours old until the Owner refreshes it from IBKR. */
    private var snapshotAgeSeconds = 5L * 3600

    fun investmentCenter() = InvestmentCenter(
        portfolio = InvestmentCenter.Portfolio(BigDecimal(1_500), BigDecimal(1_350), BigDecimal.ZERO, BigDecimal(130), BigDecimal(20), "USD",
            "2026-10-20T12:00:00+00:00", "ibkr_readonly"),
        reservedToInvestCrc = BigDecimal(100_000),
        grossPnl = BigDecimal(150), netPnl = BigDecimal(150), returnPct = BigDecimal("11.11"),
        positions = listOf(
            InvestmentCenter.Position("ETF de ejemplo", "ETF", "USD", BigDecimal(10), BigDecimal(100), BigDecimal(1_000), BigDecimal(100)),
            InvestmentCenter.Position("Acción de ejemplo", "STK", "USD", BigDecimal(5), BigDecimal(100), BigDecimal(500), BigDecimal(30)),
        ),
        syncStatus = "current", snapshotAgeSeconds = snapshotAgeSeconds, syncMethod = "flex", flexConfigured = true, includedInNetWorth = true,
        netWorthRate = InvestmentCenter.NetWorthRate(BigDecimal(500), "2026-10-20"),
    )

    fun syncIbkr(): IbkrSyncResult {
        snapshotAgeSeconds = 0
        return IbkrSyncResult("OK", 2)
    }

    private var dividendConfig = DividendPlan.Config(goalMonthlyUsd = BigDecimal(1_000), withholdingPct = BigDecimal(30))

    /**
     * Invented fixed figures: the calculation itself is the backend's (`finance/dividend_plan.py`),
     * tested there. The stock gate is closed, as for an Owner with expensive debt.
     */
    fun dividendPlan(): DividendPlan {
        val ready = dividendConfig.stocks.isNotEmpty() && dividendConfig.stocks.all { it.yieldPct != null }
        return DividendPlan(
            config = dividendConfig,
            heldSymbols = listOf("ACME"),
            gate = DividendPlan.Gate(false, listOf(DividendPlan.Gate.Blocker("expensive_debt"), DividendPlan.Gate.Blocker("salvavidas_short"))),
            result = if (!ready) DividendPlan.Result(currentValueUsd = BigDecimal(500)) else DividendPlan.Result(
                ready = true, netYieldPct = BigDecimal("2.8"), capitalNeededUsd = BigDecimal("428571.43"), currentValueUsd = BigDecimal(500),
                missingUsd = BigDecimal("428071.43"), netMonthlyDividendNowUsd = BigDecimal("1.17"), monthsToGoal = dividendConfig.monthlyAmountUsd?.let { 310 },
                monthlyNeeded = listOf(10 to 3_050, 15 to 1_850, 20 to 1_250).map { (years, amount) -> DividendPlan.Result.Horizon(years, BigDecimal(amount)) },
            ),
        )
    }

    /** Null when the request is invalid (the caller answers 422). */
    fun saveDividendPlan(update: DividendPlanUpdate): DividendPlan? {
        if (update.stocks.isEmpty() || update.stocks.fold(BigDecimal.ZERO) { sum, stock -> sum + stock.sharePct }.compareTo(BigDecimal(100)) != 0) return null
        dividendConfig = DividendPlan.Config(update.stocks, update.goalMonthlyUsd, update.monthlyAmountUsd, update.withholdingPct)
        return dividendPlan()
    }

    fun businessCenter(): BusinessCenter {
        fun total(type: String) = movements.filter { it.movementType == type }.fold(BigDecimal.ZERO) { sum, m -> sum + (m.amount ?: BigDecimal.ZERO) }
        val income = total("income")
        val expenses = total("expense")
        return BusinessCenter(businesses.toList(), movements.toList(), income, expenses, income - expenses, total("capital"))
    }

    /** Null when the request is invalid (the caller answers 422). */
    fun createBusiness(name: String?, description: String?, ownershipPct: BigDecimal?): BusinessWriteResult? {
        val trimmed = name?.trim().orEmpty()
        val ownership = ownershipPct ?: BigDecimal(100)
        if (trimmed.isEmpty() || ownership < BigDecimal.ZERO || ownership > BigDecimal(100)) return null
        val business = BusinessCenter.Business(nextId(), trimmed, description, ownership, "active")
        businesses += business
        return BusinessWriteResult(business.id)
    }

    sealed interface MovementAnswer {
        data class Saved(val result: BusinessWriteResult) : MovementAnswer
        data class Refused(val status: Int, val detail: String) : MovementAnswer
    }

    fun addMovement(businessId: Long?, type: String?, amount: BigDecimal?, date: String?, description: String?, category: String?): MovementAnswer {
        val kind = type?.trim()?.lowercase()
        if (kind !in BusinessMovementRequest.types) return MovementAnswer.Refused(400, "movement_type debe ser income, expense o capital")
        if (amount == null || amount.signum() <= 0) return MovementAnswer.Refused(422, "Monto inválido.")
        val text = description?.trim().orEmpty()
        if (text.isEmpty()) return MovementAnswer.Refused(422, "Descripción requerida.")
        if (businesses.none { it.id == businessId }) return MovementAnswer.Refused(404, "Negocio no encontrado")
        val movement = BusinessCenter.Movement(nextId(), businessId, date ?: today.toString(), kind, amount, text, category)
        movements.add(0, movement)
        return MovementAnswer.Saved(BusinessWriteResult(movement.id))
    }
}
