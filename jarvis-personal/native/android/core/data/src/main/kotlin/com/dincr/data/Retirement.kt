package com.dincr.data

import java.math.BigDecimal
import java.math.RoundingMode
import kotlinx.serialization.EncodeDefault
import kotlinx.serialization.ExperimentalSerializationApi
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * RT-1 — Plan → Retiro (VIP and the Owner): what the user has put aside for retirement (ROP and a
 * voluntary pension, declared by hand; `GET/PUT /user-product/vip/retirement`) read in simple words:
 * how much, how many years are left, and how it compares with a common age reference (a multiple of
 * the yearly income, from the normal month). Fixed rules, not investment advice. Unknown is never 0.
 * iOS twin: `Retirement.swift`.
 */
@Serializable
data class Retirement(val config: Config = Config()) {
    @Serializable
    data class Config(
        @SerialName("rop_balance") val ropBalance: Money? = null,
        @SerialName("voluntary_balance") val voluntaryBalance: Money? = null,
        @SerialName("birth_year") val birthYear: Int? = null,
        @SerialName("retire_age") val retireAge: Int? = null,
    )
}

/** `PUT /user-product/vip/retirement`: every field is sent (a null clears it). */
@OptIn(ExperimentalSerializationApi::class)
@Serializable
data class RetirementUpdate(
    @EncodeDefault(EncodeDefault.Mode.ALWAYS) @SerialName("rop_balance") val ropBalance: Money? = null,
    @EncodeDefault(EncodeDefault.Mode.ALWAYS) @SerialName("voluntary_balance") val voluntaryBalance: Money? = null,
    @EncodeDefault(EncodeDefault.Mode.ALWAYS) @SerialName("birth_year") val birthYear: Int? = null,
    @EncodeDefault(EncodeDefault.Mode.ALWAYS) @SerialName("retire_age") val retireAge: Int? = null,
)

object RetirementReading {
    /** A common reference: savings for retirement as a multiple of the yearly income, by age. */
    private val REFERENCE = listOf(25 to 0.5, 30 to 1.0, 35 to 2.0, 40 to 3.0, 45 to 4.0, 50 to 6.0, 55 to 7.0, 60 to 8.0, 67 to 10.0)

    fun multiple(age: Int): Double? {
        if (age < REFERENCE.first().first) return null
        if (age >= REFERENCE.last().first) return REFERENCE.last().second
        for ((low, high) in REFERENCE.zipWithNext()) if (age <= high.first) {
            return low.second + (high.second - low.second) * (age - low.first) / (high.first - low.first)
        }
        return null
    }

    /** The reading in short lines; empty without any balance. */
    fun lines(config: Retirement.Config, monthlyIncome: BigDecimal?, year: Int, format: MoneyFormat, language: AppLanguage = AppLanguage.current()): List<String> {
        val parts = listOfNotNull(config.ropBalance, config.voluntaryBalance)
        if (parts.isEmpty()) return emptyList()
        val total = parts.fold(BigDecimal.ZERO, BigDecimal::add)
        val lines = mutableListOf(language.pick("Tenés ${format.format(total)} ahorrado para tu retiro.", "You have ${format.format(total)} saved for retirement."))
        val birth = config.birthYear ?: return lines + language.pick("Poné tu año de nacimiento para compararlo con tu edad.", "Add your year of birth to compare it with your age.")
        val age = year - birth
        val retireAge = config.retireAge ?: 65
        if (retireAge > age) lines += language.pick("Te faltan ${retireAge - age} años para retirarte a los $retireAge.", "${retireAge - age} years are left until you retire at $retireAge.")
        val multiple = multiple(age) ?: return lines + language.pick("Lo importante ahora es empezar y aportar seguido.", "What matters now is starting and contributing regularly.")
        val income = monthlyIncome?.takeIf { it.signum() > 0 } ?: return lines
        val target = income * BigDecimal(12) * BigDecimal(multiple)
        val times = BigDecimal(multiple).setScale(1, RoundingMode.HALF_UP).stripTrailingZeros().toPlainString()
            .let { if (language == AppLanguage.SPANISH) it.replace('.', ',') else it }
        val reference = language.pick("Para tu edad, una referencia común es tener $times veces tu ingreso anual (${format.format(target)})",
            "For your age, a common reference is $times times your yearly income (${format.format(target)})")
        when {
            total >= target -> lines += reference + language.pick(": vas por encima.", ": you are above it.")
            total >= target * BigDecimal("0.8") -> lines += reference + language.pick(": vas cerca.", ": you are close.")
            else -> {
                lines += reference + language.pick(": vas por debajo.", ": you are below it.")
                val monthly = (target - total).divide(BigDecimal(60), 0, RoundingMode.UP)
                lines += language.pick("Si aportás ${format.format(monthly)} más al mes, en 5 años cerrás la diferencia.",
                    "If you add ${format.format(monthly)} more a month, you close the gap in 5 years.")
            }
        }
        return lines
    }
}
