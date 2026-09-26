package com.dincr.data

import java.math.BigDecimal
import java.math.RoundingMode

/**
 * Presentation-only money formatting from the user's profile (`base_currency`, `number_format`,
 * `currency_placement`). Never converts currencies. Same outputs as iOS `MoneyFormat`.
 */
data class MoneyFormat(
    val currency: String = "CRC",
    val separators: Separators = Separators.DOT_COMMA,
    val placement: Placement = Placement.BEFORE,
) {
    enum class Separators(val wire: String) { DOT_COMMA("dot_comma"), COMMA_DOT("comma_dot") }
    enum class Placement(val wire: String) { BEFORE("before"), AFTER("after") }
    enum class Sign { NONE, INCOME, EXPENSE }

    val symbol: String get() = when (currency.uppercase()) { "CRC" -> "₡"; "USD" -> "$"; "EUR" -> "€"; else -> currency.uppercase() }
    val fractionDigits: Int get() = if (currency.uppercase() == "CRC") 0 else 2

    fun format(amount: BigDecimal, sign: Sign = Sign.NONE, currencyOverride: String? = null): String {
        val f = currencyOverride?.let { copy(currency = it) } ?: this
        val magnitude = f.digits(amount.abs())
        val body = if (f.placement == Placement.BEFORE) "${f.symbol}$magnitude" else "$magnitude ${f.symbol}"
        val prefix = when (sign) {
            Sign.INCOME -> "+"
            Sign.EXPENSE -> "−"
            Sign.NONE -> if (amount.signum() < 0) "−" else ""
        }
        return prefix + body
    }

    /** A complete phrase for TalkBack, e.g. "menos 18.450 colones". */
    fun spoken(amount: BigDecimal, sign: Sign = Sign.NONE, language: AppLanguage = AppLanguage.current()): String {
        val negative = sign == Sign.EXPENSE || (sign == Sign.NONE && amount.signum() < 0)
        val lead = when {
            negative -> language.pick("menos ", "minus ")
            sign == Sign.INCOME -> language.pick("más ", "plus ")
            else -> ""
        }
        val plural = amount.abs().compareTo(BigDecimal.ONE) != 0
        val unit = when (currency.uppercase() to language) {
            "CRC" to AppLanguage.SPANISH, "CRC" to AppLanguage.ENGLISH -> if (plural) "colones" else "colón"
            "USD" to AppLanguage.SPANISH -> if (plural) "dólares" else "dólar"
            "USD" to AppLanguage.ENGLISH -> if (plural) "dollars" else "dollar"
            else -> currency.uppercase()
        }
        // Screen readers read display grouping literally ("257.550" can become "257 point 55" in
        // English), so the spoken form uses ungrouped digits and the language's decimal mark.
        val plain = amount.abs().setScale(fractionDigits, RoundingMode.HALF_EVEN).stripTrailingZeros().toPlainString()
        val spokenNumber = if (language == AppLanguage.SPANISH) plain.replace('.', ',') else plain
        return "$lead$spokenNumber $unit"
    }

    internal fun digits(value: BigDecimal): String {
        val scaled = value.setScale(fractionDigits, RoundingMode.HALF_EVEN).toPlainString()
        val integer = scaled.substringBefore('.')
        val fraction = scaled.substringAfter('.', "")
        val group = if (separators == Separators.DOT_COMMA) '.' else ','
        val decimal = if (separators == Separators.DOT_COMMA) ',' else '.'
        val grouped = integer.reversed().chunked(3).joinToString(group.toString()).reversed()
        return if (fraction.isEmpty()) grouped else "$grouped$decimal$fraction"
    }

    companion object {
        fun from(profile: Profile?) = MoneyFormat(
            currency = profile?.baseCurrency ?: "CRC",
            separators = Separators.entries.firstOrNull { it.wire == profile?.numberFormat } ?: Separators.DOT_COMMA,
            placement = Placement.entries.firstOrNull { it.wire == profile?.currencyPlacement } ?: Placement.BEFORE,
        )
    }
}

/**
 * Parses typed amounts. Grouping must be real thousands groups ("18.450"); a mistyped decimal
 * ("1,5" in comma_dot) is rejected instead of silently becoming 15.
 */
object AmountInput {
    fun parse(text: String, separators: MoneyFormat.Separators): BigDecimal? {
        val trimmed = text.replace(" ", "")
        if (trimmed.isEmpty()) return null
        val group = if (separators == MoneyFormat.Separators.DOT_COMMA) '.' else ','
        val decimal = if (separators == MoneyFormat.Separators.DOT_COMMA) ',' else '.'
        if (!trimmed.all { it in '0'..'9' || it == group || it == decimal }) return null
        val halves = trimmed.split(decimal)
        if (halves.size > 2) return null
        val integer = halves[0]
        val fraction = halves.getOrElse(1) { "" }
        if (integer.isEmpty() || fraction.contains(group)) return null
        val groups = integer.split(group)
        if (groups.size > 1 && (groups.first().length !in 1..3 || groups.drop(1).any { it.length != 3 })) return null
        val value = (groups.joinToString("") + if (fraction.isEmpty()) "" else ".$fraction").toBigDecimalOrNull() ?: return null
        return value.takeIf { it.signum() > 0 }
    }
}
