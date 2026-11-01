package com.dincr.data

import java.math.BigDecimal
import java.time.LocalDate

/**
 * The fake backend's Plan → Ahorro para deudas (Debug demos and tests only). Same shapes and rules as
 * FastAPI (`ai/owner_debt_blocks.py`, `ai/owner_debt_block_store.py`): one block per debt at a time
 * (409); a matured block is paid into its debt once (apply). Every name and amount is invented
 * (CLAUDE.md §4.F); the proposal is a fixed sample, not the engine. The Owner starts with one block that
 * matured yesterday, waiting for its abono. iOS twin: `FixtureBackend+DebtBlocks.swift`.
 */
internal class FakeDebtBlocks(private val today: LocalDate) {
    private val blocks = mutableListOf<DebtSavingsBlocks.Block>()
    private var maturedPaid = false
    private val matured get() = DebtSavingsBlocks.Block(id = MATURED_ID, debtId = 802, debtName = "Tarjeta de ejemplo", mode = "block",
        weeklyAmount = BigDecimal(5_000), startDate = "2026-01-01", maturityDate = today.minusDays(1).toString(), termMonths = 3,
        contributionsTotal = 13, contributionsDone = 13, savedSoFar = BigDecimal(65_000), totalAtMaturity = BigDecimal(65_000), matured = true)
    private val shown get() = (if (maturedPaid) emptyList() else listOf(matured)) + blocks

    /** One proposal while no block exists; with a block the debt is taken and nothing is left to lock. */
    fun state(): DebtSavingsBlocks {
        if (blocks.isNotEmpty()) {
            return DebtSavingsBlocks(status = "no_surplus", weeklySafeAmount = BigDecimal.ZERO, committedWeekly = BigDecimal(13_500),
                shortDebts = emptyList(), blocks = shown, warnings = listOf("average_income_estimated"))
        }
        val proposal = DebtSavingsBlocks.Proposal(
            mode = "block", debt = DebtSavingsBlocks.DebtRef(801, "Préstamo de ejemplo", BigDecimal(1_200_000), BigDecimal(24)),
            weeklyAmount = BigDecimal(13_500), contributions = 26, termMonths = 6,
            startDate = today.toString(), maturityDate = today.plusMonths(6).toString(),
            totalSaved = BigDecimal(351_000), abonoAmount = BigDecimal(351_000), balanceAtMaturity = BigDecimal(1_020_000),
            balanceAfterAbono = BigDecimal(669_000), lockCost = BigDecimal(21_400),
            recommendation = DebtSavingsBlocks.Recommendation("reduce_term", "saves_interest"))
        return DebtSavingsBlocks(status = "proposal", weeklySafeAmount = BigDecimal(13_500), committedWeekly = BigDecimal.ZERO,
            proposal = proposal, shortDebts = emptyList(), blocks = shown, warnings = listOf("average_income_estimated"))
    }

    /** The HTTP status of recording a block: 200, 409 (the debt has one) or 422 (invalid). */
    fun create(request: DebtSavingsBlockCreate?): Int {
        if (request == null || request.weeklyAmount.signum() <= 0 || request.termMonths !in 3..60) return 422
        if (blocks.any { it.debtId == request.debtId }) return 409
        val weeks = request.termMonths * 52 / 12
        blocks += DebtSavingsBlocks.Block(id = "fixture-block-${blocks.size + 1}", debtId = request.debtId, debtName = "Préstamo de ejemplo",
            mode = request.mode ?: "block", weeklyAmount = request.weeklyAmount, startDate = request.startDate,
            maturityDate = today.plusMonths(request.termMonths.toLong()).toString(), termMonths = request.termMonths,
            contributionsTotal = weeks, contributionsDone = 0, savedSoFar = BigDecimal.ZERO,
            totalAtMaturity = request.weeklyAmount * BigDecimal(weeks), nextDate = request.startDate, matured = false)
        return 200
    }

    fun cancel(id: String): Boolean = blocks.removeAll { it.id == id }

    /** The matured block paid into its debt: the answer, or null (404) when it is not open. */
    fun apply(id: String, request: DebtSavingsBlockApply?): DebtSavingsBlockApplied? {
        if (id != MATURED_ID || maturedPaid || request == null) return null
        maturedPaid = true
        return DebtSavingsBlockApplied(DebtSavingsBlockApplied.ClosedBlock(id, DebtSavingsBlockApplied.Applied(
            request.amount, request.outcome, BigDecimal(120_000), BigDecimal.ZERO)))
    }

    companion object { const val MATURED_ID = "fixture-matured-1" }
}
