package com.dincr.data

import java.math.BigDecimal
import java.time.LocalDate
import java.time.YearMonth

/**
 * Hoy (UX-6): one presentation model for the four public blocks — Estado de hoy, Para atender,
 * Qué sigue, Accesos rápidos — answering how am I, how much can I spend, what needs attention and
 * what's next. Presentation only: every figure is the backend's (or a plain sum of the backend's
 * values), unknown stays unknown (null, never 0), and no new financial rule is decided here.
 * - Free: the month's registered facts; Qué sigue is a deterministic fact or action.
 * - Basic: Free + the user's own budget left and this month's pending commitments; Qué sigue from
 *   strategy-basic ("Tu plan del mes").
 * - VIP: Basic + safe to spend and the director's one recommendation (#326 contract), and
 *   "Para atender" (#325).
 * The Owner's JARVIS space sits above these blocks in the app; it is not modelled here.
 * iOS: `HomeToday` (DincrCore).
 */
data class HomeToday(
    val tier: Tier,
    val status: HomeStatus,
    /** Null when the plan has no source for it (Free, Basic): the block is left out, never filled. */
    val attention: AttentionList.Today?,
    val next: HomeNext,
    val shortcuts: List<HomeShortcut>,
) {
    enum class Tier { FREE, BASIC, VIP }

    companion object {
        fun free(dashboard: FreeDashboard, debts: List<Debt>?, today: LocalDate = LocalDate.now()): HomeToday {
            val income = registered(dashboard.income)
            val result = if (income == null) null else dashboard.balance ?: dashboard.availableAfterCommitments
            val status = HomeStatus(HomeStatus.Headline.MONTH_RESULT, result, if (income == null) listOf(HomeInput.INCOME) else emptyList(),
                income, registered(dashboard.expenses), registered(dashboard.debtPaid), result, debtBalance(debts, dashboard.debtBalance),
                margin = null, lowestBalance = null, budget = null, pending = null)
            return HomeToday(Tier.FREE, status, null, fallbackNext(income != null, debts, today), HomeShortcut.entries)
        }

        fun basic(
            dashboard: BasicDashboard, budget: Budget?, calendar: FinancialCalendar?, plan: MonthPlan?,
            debts: List<Debt>?, today: LocalDate = LocalDate.now(),
        ): HomeToday {
            val income = registered(dashboard.income)
            val result = if (income == null) null else dashboard.balance
            val status = HomeStatus(HomeStatus.Headline.MONTH_RESULT, result, if (income == null) listOf(HomeInput.INCOME) else emptyList(),
                income, registered(dashboard.expenses), registered(dashboard.debtPaid), result, debtBalance(debts, dashboard.debt?.remaining),
                margin = null, lowestBalance = null, budget = budgetLeft(budget), pending = pending(calendar, today))
            val headline = plan?.summaryHeadline?.trim()?.takeIf { it.isNotEmpty() }
            val next = when {
                plan?.needsIncome == true -> HomeNext(HomeNext.Kind.NEEDS_INFORMATION, missing = listOf(HomeInput.INCOME), destination = HomeDestination.REGISTER_INCOME)
                headline != null -> HomeNext(HomeNext.Kind.RECOMMENDATION, title = headline, destination = HomeDestination.MONTH_PLAN)
                else -> fallbackNext(income != null, debts, today)
            }
            return HomeToday(Tier.BASIC, status, null, next, HomeShortcut.entries)
        }

        fun vip(
            center: CommandCenter, budget: Budget?, calendar: FinancialCalendar?, debts: List<Debt>?,
            mailReviewAvailable: Boolean = true, today: LocalDate = LocalDate.now(), language: AppLanguage = AppLanguage.current(),
        ): HomeToday {
            val month = center.reports?.current
            val income = registered(month?.income)
            val spend = center.safeToSpend
            val status = HomeStatus(HomeStatus.Headline.SAFE_TO_SPEND, spend?.amount,
                if (spend?.amount == null) HomeInput.codes(spend?.missing) else emptyList(),
                income, registered(month?.expenses), registered(month?.debtPaid), if (income == null) null else month?.balance,
                debtBalance(debts, null), margin = spend?.monthlyMargin, lowestBalance = spend?.next45DaysMinimum,
                budget = budgetLeft(budget), pending = pending(calendar, today))
            val director = center.director
            val headline = director?.headline?.trim()?.takeIf { it.isNotEmpty() }
            // The director needs inputs before recommending: priority `incomplete` (#326), or a known
            // priority whose target can't be chosen yet (a debt's rate is missing: `debt_interest_rates`).
            val next = when {
                director != null && (director.priority == "incomplete" || HomeInput.codes(director.missing).isNotEmpty()) ->
                    HomeInput.codes(director.missing).let { missing ->
                    HomeNext(HomeNext.Kind.NEEDS_INFORMATION, title = headline, missing = missing,
                        destination = missing.firstOrNull()?.destination ?: HomeDestination.INCOME_BASE)
                }
                headline != null -> HomeNext(HomeNext.Kind.RECOMMENDATION, title = headline,
                    detail = director?.nextAction?.trim()?.takeIf { it.isNotEmpty() }, destination = HomeDestination.MONTH_PLAN)
                else -> fallbackNext(income != null, debts, today)
            }
            return HomeToday(Tier.VIP, status, AttentionList.today(center, mailReviewAvailable, language), next, HomeShortcut.entries)
        }

        /**
         * A month's registered movements: nothing registered is unknown (missing movements don't prove
         * there were none), never shown as ₡0. No income registered also makes the result unknown.
         */
        internal fun registered(value: BigDecimal?): BigDecimal? = value?.takeIf { it.signum() > 0 }

        /** What is still owed: the debts' own balances (a plain sum), else the dashboard's figure. */
        internal fun debtBalance(debts: List<Debt>?, fallback: BigDecimal?): BigDecimal? =
            (debts?.mapNotNull { it.remainingAmount?.takeIf { amount -> amount.signum() > 0 } }?.fold(BigDecimal.ZERO, BigDecimal::add) ?: fallback)
                ?.takeIf { it.signum() > 0 }

        /** The user's own budget (never DINCR's proposal): what is left and how much is used. */
        internal fun budgetLeft(budget: Budget?): HomeStatus.BudgetLeft? {
            if (budget == null || budget.isProposal != false || budget.items.isEmpty()) return null
            val total = budget.totalBudgeted?.takeIf { it.signum() > 0 } ?: return null
            if (budget.items.any { it.spent == null }) return null
            val spent = budget.items.sumOf { it.spent!! }
            return HomeStatus.BudgetLeft(total - spent, ProgressValue.of(spent, total))
        }

        /**
         * Payments still to come this month (recurring expenses and debts from today on). A payment with
         * no known amount (0, #326) keeps the total unknown.
         */
        internal fun pending(calendar: FinancialCalendar?, today: LocalDate): HomeStatus.Pending? {
            calendar ?: return null
            val key = today.toString()
            val due = calendar.events.filter { (it.kind ?: "") in setOf("expense", "debt") && (it.date ?: "") >= key }
            val known = due.all { (it.amount ?: BigDecimal.ZERO).signum() > 0 }
            return HomeStatus.Pending(due.size, if (known) due.fold(BigDecimal.ZERO) { sum, event -> sum + event.amount!! } else null)
        }

        /**
         * Qué sigue without a strategy engine (Free, or when the engine has nothing): the next known
         * debt payment, else registering the month's income, else registering movements.
         */
        internal fun fallbackNext(incomeKnown: Boolean, debts: List<Debt>?, today: LocalDate): HomeNext {
            nextDebtPayment(debts.orEmpty(), today)?.let { (debt, date) ->
                return HomeNext(HomeNext.Kind.COMMITMENT, title = debt.name?.trim()?.takeIf { it.isNotEmpty() },
                    amount = debt.monthlyPayment?.takeIf { it.signum() > 0 }, date = date, destination = HomeDestination.DEBTS)
            }
            if (!incomeKnown) return HomeNext(HomeNext.Kind.REGISTER_INCOME, missing = listOf(HomeInput.INCOME), destination = HomeDestination.REGISTER_INCOME)
            return HomeNext(HomeNext.Kind.REGISTER_MOVEMENT, destination = HomeDestination.REGISTER_MOVEMENT)
        }

        /**
         * The earliest upcoming payment of a debt with a balance: its next payment date, or its payment
         * day this month (next month once it has passed). Debts without either have no known date.
         */
        internal fun nextDebtPayment(debts: List<Debt>, today: LocalDate): Pair<Debt, String>? {
            val key = today.toString()
            return debts.filter { (it.remainingAmount ?: BigDecimal.ZERO).signum() > 0 }.mapNotNull { debt ->
                val next = debt.nextPaymentDate?.take(10)
                if (next != null && next >= key) return@mapNotNull debt to next
                // A payment day that isn't a day of the month (stored by older flows) gives no date.
                val day = debt.paymentDay?.takeIf { it in 1..31 } ?: return@mapNotNull null
                val month = YearMonth.from(today).let { if (day < today.dayOfMonth) it.plusMonths(1) else it }
                debt to month.atDay(minOf(day, month.lengthOfMonth())).toString()
            }.minWithOrNull(compareBy<Pair<Debt, String>>({ it.second }, { it.first.id }))
        }
    }
}

/** Estado de hoy: the headline figure (null = unknown, with what is missing) and compact facts. */
data class HomeStatus(
    val headline: Headline,
    val amount: BigDecimal?,
    val missing: List<HomeInput>,
    /** Income registered this month; null when none is registered (never shown as ₡0). */
    val income: BigDecimal?,
    /** Expenses registered this month; null when none are registered. */
    val expenses: BigDecimal?,
    /** Paid to debts this month (part of the result); null when nothing is registered. */
    val debtPaid: BigDecimal?,
    /** The month's result (income − expenses − paid to debts); null while no income is registered. */
    val result: BigDecimal?,
    /** What is still owed on debts; null when nothing is owed or it is unknown. */
    val debtBalance: BigDecimal?,
    /** VIP: the month's margin from the command center; null when unknown (#326). */
    val margin: BigDecimal?,
    /** VIP: the lowest expected balance in the next 45 days. */
    val lowestBalance: BigDecimal?,
    val budget: BudgetLeft?,
    val pending: Pending?,
) {
    enum class Headline {
        /** Free and Basic: the month's result from registered movements. */
        MONTH_RESULT,
        /** VIP: safe to spend, from the command center (#326). */
        SAFE_TO_SPEND,
    }

    data class BudgetLeft(val remaining: BigDecimal, val used: ProgressValue)

    /** [total] is null when a pending payment has no known amount. */
    data class Pending(val count: Int, val total: BigDecimal?)
}

/** Qué sigue: exactly one thing. The detailed plan lives in Plan → Tu plan del mes. */
data class HomeNext(
    val kind: Kind,
    /** Backend text (recommendation, director sentence) or the commitment's name. */
    val title: String? = null,
    val detail: String? = null,
    /** Commitment amount; null when unknown. */
    val amount: BigDecimal? = null,
    /** Commitment date, `yyyy-MM-dd`. */
    val date: String? = null,
    val missing: List<HomeInput> = emptyList(),
    val destination: HomeDestination,
) {
    enum class Kind { RECOMMENDATION, NEEDS_INFORMATION, COMMITMENT, REGISTER_INCOME, REGISTER_MOVEMENT }
}

/** An input DINCR may not have (the backend's `missing` codes, #326). */
enum class HomeInput(val code: String) {
    INCOME("income"),
    ESSENTIAL_EXPENSES("essential_expenses"),
    DEBT_PAYMENTS("debt_payments"),
    SAVINGS("savings"),
    EMERGENCY_FUND_TARGET("emergency_fund_target"),
    /** A debt's interest rate, needed to choose which debt to pay down first. */
    DEBT_INTEREST_RATES("debt_interest_rates");

    /**
     * Where the user gives DINCR this input, in the flows that exist (never an estimate): income is
     * registered as a movement (salary / pay stub), debts in Deudas, essential expenses in Plan →
     * Ingresos y base, savings and the emergency-fund target in Metas y ahorros → Tus ahorros (UX-7:
     * there is no separate Situación screen).
     */
    val destination: HomeDestination get() = when (this) {
        INCOME -> HomeDestination.REGISTER_INCOME
        DEBT_PAYMENTS, DEBT_INTEREST_RATES -> HomeDestination.DEBTS
        ESSENTIAL_EXPENSES -> HomeDestination.INCOME_BASE
        SAVINGS, EMERGENCY_FUND_TARGET -> HomeDestination.GOALS
    }

    companion object {
        /** Known codes in the backend's order; codes this app doesn't know are skipped. */
        fun codes(codes: List<String>?): List<HomeInput> = codes.orEmpty().mapNotNull { code -> entries.firstOrNull { it.code == code } }
    }
}

/** Screens Hoy opens. All exist on both platforms; [route] is the app's own route (null: not a route). */
enum class HomeDestination(val route: String?) {
    REGISTER_INCOME(null), REGISTER_MOVEMENT(null), MOVEMENTS("movements"), DEBTS("debts"), GOALS("goals"),
    INCOME_BASE("incomeBase"), MONTH_PLAN("strategy"),
}

/** Accesos rápidos: the same essentials for every plan. */
enum class HomeShortcut(val destination: HomeDestination) {
    REGISTER_MOVEMENT(HomeDestination.REGISTER_MOVEMENT),
    MOVEMENTS(HomeDestination.MOVEMENTS),
    DEBTS(HomeDestination.DEBTS),
    GOALS(HomeDestination.GOALS),
}
