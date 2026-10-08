package com.dincr.data

import java.math.BigDecimal

/**
 * §15 PR 8 — Patrimonio → Deudas: how the active debts make up what is owed, from the balances kept
 * in Plan → Deudas (`remaining_amount`). Presentation only: nothing is computed but the shares
 * [Composition] allows. A paid debt (balance 0) is left out; a debt whose balance is unknown is kept
 * as unknown, so no share or total is drawn from it (never read as 0). Debts carry no currency of
 * their own: they are the account's base currency. iOS: `DincrCore.DebtComposition`.
 */
object DebtComposition {
    fun of(debts: List<Debt>): Composition = Composition(
        debts.filter { debt -> debt.remainingAmount?.let { it > BigDecimal.ZERO } ?: true }
            .map { CompositionItem("debt-${it.id}", it.name.orEmpty(), it.remainingAmount) },
    )
}
