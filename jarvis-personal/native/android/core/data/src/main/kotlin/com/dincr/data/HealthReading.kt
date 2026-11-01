package com.dincr.data

import java.math.BigDecimal
import java.math.RoundingMode

/**
 * HS-1 — "Tu salud financiera" in simple words (VIP and the Owner): one word, the main reason and one
 * thing to do, no score and no technical figures. From what the app already reads: a normal month
 * ([FinancialReading.Normal]) and how many months the Salvavidas covers (`/vip/salvavidas`
 * coverage_months). Fixed rules, not advice. Unknown is never zero: without a normal month there is no
 * reading; an unknown Salvavidas is left out. iOS twin: `HealthReading.swift`.
 */
object HealthReading {
    enum class Level { GOOD, FAIR, AT_RISK }

    data class Reading(val level: Level, val word: String, val reason: String, val action: String)

    fun reading(normal: FinancialReading.Normal?, coverageMonths: BigDecimal?, language: AppLanguage = AppLanguage.current()): Reading? {
        normal ?: return null
        val debtShare = FinancialReading.per100(normal.debtPaid, normal.income) ?: 0
        val savedShare = FinancialReading.per100(normal.saved, normal.income) ?: 0
        fun make(level: Level, reason: String, action: String) = Reading(level, when (level) {
            Level.GOOD -> language.pick("Bien", "Good")
            Level.FAIR -> language.pick("Regular", "Fair")
            Level.AT_RISK -> language.pick("En riesgo", "At risk")
        }, reason, action)
        // "1,5" / "1.5" meses; a whole number without decimals.
        val months = coverageMonths?.setScale(1, RoundingMode.HALF_UP)?.stripTrailingZeros()?.toPlainString()
            ?.let { if (language == AppLanguage.SPANISH) it.replace('.', ',') else it }
        val cover = coverageMonths?.toDouble()

        if (normal.left.signum() < 0) return make(Level.AT_RISK,
            language.pick("En un mes normal sale más plata de la que entra.", "In a normal month more money goes out than comes in."),
            language.pick("Revisá tu gasto más grande en Resumen del mes y bajalo un poco.", "Check your biggest spending in Monthly summary and lower it a little."))
        if (debtShare >= 40) return make(Level.AT_RISK,
            language.pick("Las deudas se llevan $debtShare de cada 100 que entran.", "Debts take $debtShare of every 100 that come in."),
            language.pick("Probá en Plan → Escenarios si refinanciar o juntar deudas te baja la cuota.", "Try in Plan → Scenarios whether refinancing or consolidating lowers your payment."))
        if (cover != null && cover < 0.5) return make(Level.AT_RISK,
            language.pick("Tu Salvavidas cubre $months meses de tus obligaciones.", "Your emergency fund covers $months months of your obligations."),
            language.pick("Apartá algo cada semana para tu Salvavidas hasta cubrir un mes.", "Put something aside every week for your emergency fund until it covers a month."))
        if (savedShare < 10) return make(Level.FAIR,
            language.pick("Guardás $savedShare de cada 100 que entran.", "You save $savedShare of every 100 that come in."),
            language.pick("Subí lo que guardás poco a poco hasta 10 de cada 100.", "Raise what you save little by little up to 10 of every 100."))
        if (debtShare >= 20) return make(Level.FAIR,
            language.pick("Las deudas se llevan $debtShare de cada 100 que entran.", "Debts take $debtShare of every 100 that come in."),
            language.pick("Lo que te sobre, mandalo a la deuda más cara.", "Send what is left to your most expensive debt."))
        if (cover != null && cover < 3) return make(Level.FAIR,
            language.pick("Tu Salvavidas cubre $months meses; lo ideal son tres.", "Your emergency fund covers $months months; three is the aim."),
            language.pick("Seguí con tu aporte al Salvavidas hasta llegar a tres meses.", "Keep contributing to your emergency fund until it reaches three months."))
        return make(Level.GOOD,
            language.pick("Te sobra plata, guardás y tus deudas están bajo control.", "You have money left, you save and your debts are under control."),
            language.pick("Seguí así y pensá en tu próxima meta.", "Keep it up and think about your next goal."))
    }
}
