package com.dincr.data

import java.math.BigDecimal
import java.math.RoundingMode
import java.time.LocalDate
import java.time.temporal.ChronoUnit
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.jsonPrimitive

/**
 * The fake backend's Salvavidas automatic contributions (Debug demos and UI tests only), mirroring
 * `backend/finance/salvavidas_plan.py` and `emergency_fund.py`: every scheduled date after the day the
 * balance was declared, up to today (and not after the end date), adds the amount; the Owner's rate
 * adds simple daily interest. Derived when read; a read never writes. iOS: `FixtureBackend+Salvavidas`.
 */
internal class FakeSalvavidasPlan(private val today: LocalDate) {
    private var plan: Salvavidas.AutoContribution? = null
    private var baseDate: LocalDate? = null
    var ownerRate: BigDecimal? = null
        private set

    /** What the stored plan added to [base] (`auto_contribution`), or null without a plan. */
    fun answer(base: BigDecimal, interestRate: BigDecimal?): Salvavidas.AutoContribution? {
        val stored = plan ?: return null
        val start = LocalDate.parse(stored.startDate)
        val from = baseDate ?: start.minusDays(1)
        val amount = stored.amount ?: BigDecimal.ZERO
        val dates = if (stored.isEnabled) scheduled(stored, from, today) else emptyList()
        val contributions = amount * BigDecimal(dates.size)
        var interest = BigDecimal.ZERO
        if (stored.isEnabled && interestRate != null && interestRate.signum() > 0) {
            val rate = interestRate.divide(BigDecimal(100))
            fun simple(principal: BigDecimal, since: LocalDate) =
                (principal * rate * BigDecimal(ChronoUnit.DAYS.between(since, today).coerceAtLeast(0))).divide(BigDecimal(365), 10, RoundingMode.HALF_UP)
            interest = (dates.fold(simple(base, from)) { sum, day -> sum + simple(amount, day) }).setScale(2, RoundingMode.HALF_UP)
        }
        val next = if (stored.isEnabled) scheduled(stored, today, today.plusYears(2)).firstOrNull() else null
        return stored.copy(
            baseAmount = base, baseDate = from.toString(), contributionsCount = dates.size, contributionsAmount = contributions,
            estimatedInterest = interest, nextDate = next?.toString(), total = base + contributions + interest,
        )
    }

    /** The plan and rate parts of a PUT, validated; a refusal (422 detail) changes nothing. */
    data class Change(val plan: Salvavidas.AutoContribution?, val rate: BigDecimal?)

    fun validate(body: JsonObject?, owner: Boolean, balanceKnown: Boolean): Pair<Change?, String?> {
        fun field(key: String) = body?.get(key)?.takeIf { it !is JsonNull }
        var rate: BigDecimal? = null
        field("annual_interest_rate")?.let { raw ->
            if (!owner) return null to "La tasa de interés del Salvavidas no está disponible en tu plan."
            rate = raw.jsonPrimitive.content.toBigDecimalOrNull()?.takeIf { it.signum() >= 0 && it <= SalvavidasRateInput.MAX_RATE }
                ?: return null to "Indicá una tasa de interés anual entre 0 % y 50 %."
        }
        var checked: Salvavidas.AutoContribution? = null
        field("auto_contribution")?.let { raw ->
            val item = raw as? JsonObject ?: return null to "Los aportes automáticos no son válidos."
            fun text(key: String) = (item[key] as? JsonPrimitive)?.takeIf { it !is JsonNull }?.content
            val amount = text("amount")?.toBigDecimalOrNull()?.takeIf { it.signum() > 0 && it <= SalvavidasPlanRequest.MAX_AMOUNT }
                ?: return null to "Indicá un monto de aporte mayor que cero."
            val frequency = text("frequency")?.takeIf { it in Salvavidas.AutoContribution.FREQUENCIES }
                ?: return null to "La frecuencia debe ser semanal, quincenal o mensual."
            val start = text("start_date")?.let { runCatching { LocalDate.parse(it) }.getOrNull() }
                ?: return null to "Indicá la fecha del primer aporte."
            val end = text("end_date")?.takeIf { it.isNotEmpty() }?.let { value ->
                runCatching { LocalDate.parse(value) }.getOrNull()?.takeIf { !it.isBefore(start) }
                    ?: return null to "La fecha final debe ser después del primer aporte."
            }
            val enabled = (item["enabled"] as? JsonPrimitive)?.booleanOrNull ?: false
            if (enabled && !balanceKnown) return null to "Indicá cuánto tenés ahorrado hoy (puede ser 0) para activar los aportes automáticos."
            checked = Salvavidas.AutoContribution(enabled, amount, frequency, start.toString(), end?.toString())
        }
        return Change(checked, rate) to null
    }

    /** Declaring the balance restarts the count from today; turning the plan on counts from today. */
    fun apply(change: Change, declaredNow: Boolean) {
        change.rate?.let { ownerRate = it }
        if (declaredNow) baseDate = today
        change.plan?.let { next ->
            if (next.isEnabled && plan?.isEnabled != true && !declaredNow) baseDate = today
            plan = next
        }
    }

    companion object {
        /** Scheduled days d with `after < d <= until`, within the plan's start and end. */
        fun scheduled(plan: Salvavidas.AutoContribution, after: LocalDate, until: LocalDate): List<LocalDate> {
            val start = plan.startDate?.let { LocalDate.parse(it) } ?: return emptyList()
            val end = plan.endDate?.let { LocalDate.parse(it) } ?: until
            val last = if (end.isBefore(until)) end else until
            val days = mutableListOf<LocalDate>()
            for (index in 0 until 5000) {
                val day = when (plan.frequency) {
                    "monthly" -> start.plusMonths(index.toLong())
                    "biweekly" -> start.plusDays(index * 14L)
                    else -> start.plusDays(index * 7L)
                }
                if (day.isAfter(last)) break
                if (day.isAfter(after)) days += day
            }
            return days
        }
    }
}
