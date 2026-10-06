package com.dincr.data

import java.math.BigDecimal
import java.math.RoundingMode
import java.time.LocalDate
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonPrimitive

/**
 * The Plan, Salvavidas and Owner-analysis answers of [FakeBackend] (Debug demos and UI tests only).
 * They mirror the backend's shapes (`ai/strategy_dashboard.py`, `finance/emergency_fund.py`,
 * `transactions/analyzer.py`, `finance/service.py`, `finance/strategic_engine.py`) on the fake's
 * synthetic data; every name and amount is invented. The Users answers never read Owner data, and
 * the Owner answers exist only for the server role owner.
 */
internal class FakePlanRoutes(private val json: Json, private val today: LocalDate) {
    /** The fake account's data, read fresh on every request. */
    data class Snapshot(
        val movements: List<Movement>,
        val debts: List<Debt>,
        val goals: List<Goal>,
        val savings: List<SavingsPlan>,
        val recurring: List<RecurringItem>,
        val situation: FinancialProfile?,
    )

    private var targetMonths = 6
    // The Owner's historical Salvavidas: a manual balance and a protected-expense picker (synthetic).
    private var ownerAmount = BigDecimal(300_000)
    private var ownerProtected = listOf(31L)
    private val ownerMandatory = listOf(Salvavidas.Expense(30, "Vivienda de ejemplo", BigDecimal(210_000), "monthly", 1, true))
    private val ownerOptional = listOf(
        Salvavidas.Expense(31, "Gimnasio de ejemplo", BigDecimal(25_000), "monthly", 10),
        Salvavidas.Expense(32, "Streaming de ejemplo", BigDecimal(6_000), "monthly", 20),
    )

    private val month get() = today.toString().take(7)

    private fun monthTotals(rows: List<Movement>, period: String): Pair<BigDecimal, BigDecimal> {
        val inMonth = rows.filter { it.transactionDate?.startsWith(period) == true }
        return inMonth.filter { it.kind == MovementKind.INCOME }.sumOf { it.amount } to inMonth.filter { it.kind == MovementKind.EXPENSE }.sumOf { it.amount }
    }

    /** strategy-basic `income_source`: declared salary first, else recorded income, else none. */
    fun basicIncome(data: Snapshot): Pair<String, BigDecimal> {
        data.situation?.fixedMonthlySalary?.takeIf { it.signum() > 0 }?.let { return "declared" to it }
        val observed = data.movements.filter { it.kind == MovementKind.INCOME }
            .groupBy { it.transactionDate?.take(7) }.values.maxOfOrNull { rows -> rows.sumOf { it.amount } }
        return if (observed != null && observed.signum() > 0) "observed" to observed else "none" to BigDecimal.ZERO
    }

    // --- Strategy dashboards ----------------------------------------------------------------------

    fun strategyDashboard(data: Snapshot, owner: Boolean, role: String?): String {
        val (incomeSource, income) = basicIncome(data)
        val (_, spent) = monthTotals(data.movements, month)
        val active = data.debts.filter { (it.remainingAmount ?: BigDecimal.ZERO).signum() > 0 }
        val debtCommitment = active.sumOf { it.monthlyPayment ?: BigDecimal.ZERO }
        val pendingRecurring = data.recurring.filter { it.isActive == true && it.itemType == "expense" && (it.dueDay ?: 0) > today.dayOfMonth }.sumOf { it.amount ?: BigDecimal.ZERO }
        val statement = if (owner) BigDecimal(95_000) else BigDecimal.ZERO
        val mandatoryPending = if (owner) BigDecimal(210_000) else BigDecimal.ZERO
        val before = income - spent - debtCommitment - pendingRecurring - statement - mandatoryPending
        val surplus = before.max(BigDecimal.ZERO)
        val deficit = before.negate().max(BigDecimal.ZERO)
        val target = active.maxByOrNull { it.interestRate ?: BigDecimal.ZERO }
        fun part(pct: Int) = surplus.multiply(BigDecimal(pct)).divide(BigDecimal(100), 2, RoundingMode.HALF_UP)
        val items = if (surplus.signum() == 0) emptyList() else listOf(
            DirectorStrategy.AllocationItem("ataque_de_deuda", 45.0, part(45), target?.name),
            DirectorStrategy.AllocationItem("fondo_de_emergencia", 40.0, part(40)),
            DirectorStrategy.AllocationItem("vida_controlada", 15.0, surplus - part(45) - part(40)),
        )
        val formula = linkedMapOf<String, BigDecimal>()
        if (owner) formula["cash_available_now"] = BigDecimal(640_000)
        formula["income"] = income
        if (owner) { formula["statement_spending"] = statement; formula["new_spending_after_cut"] = spent } else formula["recorded_spending"] = spent
        formula["debt_commitment"] = debtCommitment
        if (owner) formula["mandatory_fixed_pending"] = mandatoryPending else formula["pending_recurring"] = pendingRecurring
        formula["surplus"] = surplus
        formula["deficit"] = deficit
        val timeline = active.sortedByDescending { it.interestRate ?: BigDecimal.ZERO }.mapIndexed { index, debt ->
            DirectorStrategy.TimelineItem(index + 1, debt.name, debt.remainingAmount,
                (debt.monthlyPayment ?: BigDecimal.ZERO) + if (index == 0) part(45) else BigDecimal.ZERO, today.plusMonths(14L + 10 * index).withDayOfMonth(1).toString())
        }
        val status = when { income.signum() <= 0 -> "needs_income"; surplus.signum() == 0 -> "critical"; active.isNotEmpty() -> "controlled"; else -> "strong" }
        val total = active.sumOf { it.remainingAmount ?: BigDecimal.ZERO }
        val original = data.debts.sumOf { (it.totalAmount ?: BigDecimal.ZERO).max(it.remainingAmount ?: BigDecimal.ZERO) }
        val strategy = DirectorStrategy(
            scope = if (owner) "owner" else "users", status = status, month = month, title = "Director Financiero · DEBT ATTACK", modeLabel = "DEBT ATTACK",
            objective = if (status == "needs_income") "Registrá o declará tus ingresos para que DINCR pueda repartir tu sobrante." else "Modo DEBT ATTACK: se acelera la deuda sin dejar de construir seguridad.",
            priority = target?.let { DirectorStrategy.Priority("debt", "Atacar deuda: ${it.name}", "El sobrante destinado a deuda se concentra primero en esta obligación.") },
            monthlyIncome = income,
            // The backend income policy's own values: "declared" or, without a declared income, "recorded".
            incomePolicy = DirectorStrategy.IncomePolicy("income-policy-v1", if (incomeSource == "declared") "declared" else if (incomeSource == "none") "none" else "recorded"),
            monthlyExpenses = spent, debtCommitmentCurrentCycle = debtCommitment, pendingRecurringTotal = if (owner) null else pendingRecurring,
            safeToSpend = part(15),
            // Like the backend director: unknown Users savings count as 0 here; `salvavidas` says they are unknown.
            emergencyFund = DirectorStrategy.EmergencyFund(if (owner) ownerAmount else data.situation?.liquidSavings ?: BigDecimal.ZERO,
                BigDecimal(119_900), BigDecimal(119_900), BigDecimal(119_900), "one_month_building"),
            salvavidas = if (owner) ownerSalvavidas(data) else usersSalvavidas(data),
            timeline = timeline, estimatedDebtFreeDate = timeline.lastOrNull()?.estimatedPayoffDate, totalDebt = total,
            debtProgressPercent = if (original.signum() > 0) (original - total).multiply(BigDecimal(100)).divide(original, 2, RoundingMode.HALF_UP).toDouble() else 0.0,
            investmentRecommended = BigDecimal.ZERO,
            rules = listOf("Solo se distribuye el sobrante que queda después de obligaciones y gastos ya registrados."),
            allocationBaseAmount = surplus, allocationItems = items,
            distributionFormula = formula.mapValues { JsonPrimitive(it.value) },
            distributableAccountCash = if (owner) BigDecimal(640_000) else null,
            recurringMonthlyIncome = if (owner) income else null,
            currentMonthExtraNet = if (owner) BigDecimal(45_000) else null,
            incomeReceivedCurrentCycle = if (owner) BigDecimal(432_500) else null,
            remainingIncomeCurrentCycle = if (owner) income else null,
            statementExpenses = if (owner) statement else null,
            newExpensesAfterCut = if (owner) spent else null,
            mandatoryFixedPending = if (owner) mandatoryPending else null,
            mandatoryFixedPendingItems = if (owner) listOf(DirectorStrategy.PendingItem("Vivienda de ejemplo", mandatoryPending, today.plusDays(3).toString())) else emptyList(),
            investmentPortfolio = if (owner) DirectorStrategy.InvestmentPortfolio(BigDecimal(1_500), BigDecimal(1_400), BigDecimal(100), "USD") else null,
            baseTimeline = if (owner) timeline else emptyList(),
            monthsSavedByCurrentExtras = if (owner) 2 else null,
        )
        return json.encodeToString(StrategyDashboard("OK", role, strategy.title, strategy.objective, strategy, "live_database"))
    }

    // --- Salvavidas ---------------------------------------------------------------------------------

    fun salvavidas(data: Snapshot, owner: Boolean): String = json.encodeToString(if (owner) ownerSalvavidas(data) else usersSalvavidas(data))

    /**
     * PUT. Users: the target and their declared savings (the financial situation's liquid savings,
     * returned as the third value for the fake to store; 422 without a situation) — never protected
     * expenses. The Owner: target, manual balance and protected expenses.
     */
    fun updateSalvavidas(data: Snapshot, owner: Boolean, target: Int?, amount: BigDecimal?, protectedIds: List<Long>?): Triple<Int, String, FinancialProfile?> {
        if (target != null && target !in Salvavidas.ALLOWED_TARGET_MONTHS) return Triple(422, "El objetivo del Salvavidas debe ser de 1, 3 o 6 meses.", null)
        if (amount != null && amount.signum() < 0) return Triple(422, "El ahorro no puede ser negativo.", null)
        if (!owner && !protectedIds.isNullOrEmpty()) return Triple(422, "En DINCR todas tus obligaciones cuentan para el Salvavidas.", null)
        if (!owner && amount != null && data.situation == null) return Triple(422, "Declará primero tus ingresos para guardar tus ahorros.", null)
        target?.let { targetMonths = it }
        if (owner) {
            amount?.let { ownerAmount = it }
            protectedIds?.let { ids -> ownerProtected = ids.filter { id -> ownerOptional.any { it.id == id } }.distinct() }
            return Triple(200, salvavidas(data, true), null)
        }
        val situation = amount?.let { data.situation?.copy(liquidSavings = it) }
        return Triple(200, salvavidas(if (situation != null) data.copy(situation = situation) else data, false), situation)
    }

    private fun debtLines(data: Snapshot) = data.debts.filter { (it.remainingAmount ?: BigDecimal.ZERO).signum() > 0 }
        .map { Salvavidas.DebtLine(it.id, it.name, it.monthlyPayment ?: BigDecimal.ZERO) }

    private fun milestones(base: BigDecimal, current: BigDecimal?) = Salvavidas.ALLOWED_TARGET_MONTHS.map { months ->
        val target = base * BigDecimal(months)
        Salvavidas.Milestone(months, target, current != null && base.signum() > 0 && current >= target)
    }

    private fun ratio(part: BigDecimal, whole: BigDecimal) = part.divide(whole, 2, RoundingMode.HALF_UP)

    private fun usersSalvavidas(data: Snapshot): Salvavidas {
        val debts = debtLines(data)
        val obligations = data.recurring.filter { it.isActive == true && it.itemType == "expense" }
            .map { Salvavidas.Expense(it.id, it.name, it.amount ?: BigDecimal.ZERO, it.frequency ?: "monthly", it.dueDay) }
        val debtMonthly = debts.sumOf { it.monthlyPayment ?: BigDecimal.ZERO }
        val recurringMonthly = obligations.sumOf { it.monthlyAmount ?: BigDecimal.ZERO }
        val base = debtMonthly + recurringMonthly
        val target = base * BigDecimal(targetMonths)
        val current = data.situation?.liquidSavings
        return Salvavidas(
            status = if (base.signum() > 0) "OK" else "needs_obligations", scope = "users",
            currentAmount = current, currentAmountKnown = current != null, monthlyBase = base, targetMonths = targetMonths,
            allowedTargetMonths = Salvavidas.ALLOWED_TARGET_MONTHS, targetAmount = target,
            missingAmount = current?.let { (target - it).max(BigDecimal.ZERO) },
            coverageMonths = current?.takeIf { base.signum() > 0 }?.let { ratio(it, base) },
            progressPercent = current?.takeIf { target.signum() > 0 }?.let { ratio(it * BigDecimal(100), target).min(BigDecimal(100)).toDouble() },
            components = Salvavidas.Components(debtMonthlyPayments = debtMonthly, recurringObligations = recurringMonthly),
            debts = debts, obligations = obligations, milestones = milestones(base, current),
            verification = Salvavidas.Verification("declared", message = if (current != null) "El fondo es el ahorro disponible que declaraste."
                else "Declará tus ahorros disponibles para medir la cobertura."),
        )
    }

    private fun ownerSalvavidas(data: Snapshot): Salvavidas {
        val debts = debtLines(data)
        val debtMonthly = debts.sumOf { it.monthlyPayment ?: BigDecimal.ZERO }
        val mandatory = ownerMandatory.sumOf { it.monthlyAmount ?: BigDecimal.ZERO }
        val optional = ownerOptional.map { it.copy(selected = it.id in ownerProtected) }
        val protected = optional.filter { it.selected == true }.sumOf { it.monthlyAmount ?: BigDecimal.ZERO }
        val base = debtMonthly + mandatory + protected
        val target = base * BigDecimal(targetMonths)
        return Salvavidas(
            status = "OK", scope = "owner", currentAmount = ownerAmount, monthlyBase = base, targetMonths = targetMonths, targetAmount = target,
            missingAmount = (target - ownerAmount).max(BigDecimal.ZERO), coverageMonths = if (base.signum() > 0) ratio(ownerAmount, base) else BigDecimal.ZERO,
            progressPercent = if (target.signum() > 0) ratio(ownerAmount * BigDecimal(100), target).min(BigDecimal(100)).toDouble() else 0.0,
            protectedExpenseIds = ownerProtected,
            components = Salvavidas.Components(debtMonthlyPayments = debtMonthly, mandatoryFixedExpenses = mandatory, protectedExpenses = protected),
            debts = debts, mandatoryExpenses = ownerMandatory, availableExpenses = optional,
            milestones = milestones(base, ownerAmount),
            verification = Salvavidas.Verification("manual", false, "Guardá el saldo para crear y vincular la cuenta financiera Salvavidas."),
        )
    }

    // --- Owner analysis (Owner routers) -------------------------------------------------------

    fun analysis(data: Snapshot): String {
        val months = (5 downTo 0).map { today.minusMonths(it.toLong()).toString().take(7) }
        var cumulative = BigDecimal.ZERO
        val flow = months.map { m ->
            val (income, expenses) = monthTotals(data.movements, m)
            cumulative += income - expenses
            TransactionAnalysis.FlowMonth(m, income, expenses, income - expenses, cumulative)
        }
        val ytd = data.movements.filter { it.kind == MovementKind.EXPENSE && it.transactionDate?.startsWith(today.year.toString()) == true }
        val categories = ytd.groupBy { it.category ?: "Sin categoría" }
            .map { (category, rows) -> TransactionAnalysis.Category(category, rows.sumOf { it.amount }, rows.size) }.sortedByDescending { it.total }
        val income = data.movements.filter { it.kind == MovementKind.INCOME }.sumOf { it.amount }
        val expenses = data.movements.filter { it.kind == MovementKind.EXPENSE }.sumOf { it.amount }
        return json.encodeToString(TransactionAnalysis(
            TransactionAnalysis.Summary(income, expenses, BigDecimal.ZERO, income - expenses, data.movements.size),
            TransactionAnalysis.SpendingBreakdown(TransactionAnalysis.Period("${today.year}-01-01", today.toString(), "${today.year} YTD"), ytd.sumOf { it.amount }, categories),
            flow, flow.map { TransactionAnalysis.MonthTotal(it.month, it.expenses) },
        ))
    }

    fun netWorth(data: Snapshot): String {
        val savingsTotal = data.savings.sumOf { it.savedAmount ?: BigDecimal.ZERO } + ownerAmount
        val debtTotal = data.debts.sumOf { it.remainingAmount ?: BigDecimal.ZERO }
        val net = savingsTotal - debtTotal
        return json.encodeToString(NetWorthReport(
            NetWorthReport.Assets(savingsTotal, BigDecimal.ZERO, savingsTotal),
            NetWorthReport.Liabilities(debtTotal, data.debts.sumOf { it.monthlyPayment ?: BigDecimal.ZERO }),
            net, NetWorthReport.Change(BigDecimal(25_000), 1.2), if (net.signum() < 0) "negative" else "positive", "medium_high",
            "Tu patrimonio neto es negativo porque tus deudas superan tus activos.", "Reducir deudas de mayor interés y aumentar activos líquidos.",
            listOf("Revisar deudas con interés alto para aplicar avalancha o refinanciamiento."),
        ))
    }

    fun engine(data: Snapshot): String {
        val (income, expenses) = monthTotals(data.movements, month)
        val top = data.debts.maxByOrNull { it.interestRate ?: BigDecimal.ZERO }
        return json.encodeToString(FinancialEngineReport(
            "OK", FinancialEngineReport.Health(54.5, "stable", 1.0),
            FinancialEngineReport.Forecast("OK", month, income - expenses),
            FinancialEngineReport.EmergencyFund(ownerAmount, BigDecimal(119_900), BigDecimal("2.50"), BigDecimal(719_400)),
            FinancialEngineReport.Debts("OK", FinancialEngineReport.Plan("avalanche", top?.let { FinancialEngineReport.PriorityDebt(it.name, it.remainingAmount, it.interestRate?.toDouble()) }),
                FinancialEngineReport.MinimumCost(data.debts.sumOf { it.remainingAmount ?: BigDecimal.ZERO }, data.debts.sumOf { it.monthlyPayment ?: BigDecimal.ZERO })),
            listOfNotNull(top?.let { "Prioridad avalancha: ${it.name}." }),
        ))
    }
}
