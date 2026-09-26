package com.dincr.data

import java.math.BigDecimal
import java.math.RoundingMode

/**
 * Presentation-only money formatting from the user's profile (`base_currency`, `number_format`,
 * `currency_placement`). Never converts currencies. Same outputs as iOS `MoneyFormat`.
 * Display rounding (colones without decimals) is visual only: edit forms use [inputText].
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
        // A currency code (legacy bases such as ARS) is a word, so it gets a space: "ARS 1.234,00".
        val gap = if (f.symbol.length > 1) " " else ""
        val body = if (f.placement == Placement.BEFORE) "${f.symbol}$gap$magnitude" else "$magnitude ${f.symbol}"
        val prefix = when (sign) {
            Sign.INCOME -> "+"
            Sign.EXPENSE -> "−"
            Sign.NONE -> if (amount.signum() < 0) "−" else ""
        }
        return prefix + body
    }

    /**
     * A complete phrase for TalkBack, e.g. "menos 18.450 colones". [currencyOverride] names the
     * unit when the amount is not in the base currency, exactly like [format].
     */
    fun spoken(amount: BigDecimal, sign: Sign = Sign.NONE, language: AppLanguage = AppLanguage.current(), currencyOverride: String? = null): String {
        if (currencyOverride != null && !currencyOverride.equals(currency, ignoreCase = true)) {
            return copy(currency = currencyOverride).spoken(amount, sign, language)
        }
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
            "EUR" to AppLanguage.SPANISH, "EUR" to AppLanguage.ENGLISH -> if (plural) "euros" else "euro"
            else -> currency.uppercase()
        }
        // Screen readers read display grouping literally ("257.550" can become "257 point 55" in
        // English), so the spoken form uses ungrouped digits and the language's decimal mark.
        val plain = amount.abs().setScale(fractionDigits, RoundingMode.HALF_UP).stripTrailingZeros().toPlainString()
        val spokenNumber = if (language == AppLanguage.SPANISH) plain.replace('.', ',') else plain
        return "$lead$spokenNumber $unit"
    }

    /**
     * The stored amount as the user would type it (their separators, no symbol, no rounding),
     * for prefilling an edit form. [AmountInput.parse] reads it back to the same value.
     */
    fun inputText(amount: BigDecimal): String {
        val plain = amount.abs().stripTrailingZeros().let { if (it.scale() < 0) it.setScale(0) else it }
        return group(plain.setScale(minOf(plain.scale(), AmountInput.MAX_FRACTION_DIGITS), RoundingMode.HALF_UP).toPlainString())
    }

    // Half away from zero, like the Capacitor app's Intl.NumberFormat (₡2,5 → ₡3).
    internal fun digits(value: BigDecimal): String = group(value.setScale(fractionDigits, RoundingMode.HALF_UP).toPlainString())

    private fun group(plain: String): String {
        val integer = plain.substringBefore('.')
        val fraction = plain.substringAfter('.', "")
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
 * Parses typed amounts. Returns null for anything that is not an unambiguous positive amount;
 * nothing is guessed. Grouping must be real thousands groups ("18.450"); a mistyped decimal
 * ("1,5" in comma_dot) is rejected instead of silently becoming 15. Same rules as iOS.
 */
object AmountInput {
    /** Money never has more than two decimals; this also rejects "1.000" in comma_dot. */
    const val MAX_FRACTION_DIGITS = 2
    /** Below a trillion: far above any personal amount, keeps accidental pastes out. */
    const val MAX_INTEGER_DIGITS = 12

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
        if (integer.isEmpty() || fraction.contains(group) || fraction.length > MAX_FRACTION_DIGITS) return null
        val groups = integer.split(group)
        if (groups.size > 1 && (groups.first().length !in 1..3 || groups.drop(1).any { it.length != 3 })) return null
        if (groups.joinToString("").trimStart('0').length > MAX_INTEGER_DIGITS) return null
        val value = (groups.joinToString("") + if (fraction.isEmpty()) "" else ".$fraction").toBigDecimalOrNull() ?: return null
        return value.takeIf { it.signum() > 0 }
    }
}
