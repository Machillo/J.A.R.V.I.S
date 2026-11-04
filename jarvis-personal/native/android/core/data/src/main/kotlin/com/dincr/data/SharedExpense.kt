package com.dincr.data

import java.math.BigDecimal

/**
 * What a text shared into DINCR (a bank's SMS or notice) proposes for a new expense: its amount, its
 * currency and where. Deterministic rules, on the device: the text is never stored, logged or sent, and
 * nothing is recorded until the user saves the editor. What can't be read stays empty, to type it.
 */
data class SharedExpense(val amount: BigDecimal?, val currency: String?, val merchant: String?) {
    companion object {
        private const val MAX_TEXT = 2_000
        private const val NUMBER = """\d[\d.,]*"""
        private val SYMBOL_FIRST = Regex("""(₡|US\$|\$|USD|CRC)\s*($NUMBER)""", RegexOption.IGNORE_CASE)
        private val SYMBOL_LAST = Regex("""($NUMBER)\s*(USD|CRC|colones|d[oó]lares)\b""", RegexOption.IGNORE_CASE)
        private val LABELED_MERCHANT = Regex("""(?:comercio|establecimiento|merchant)\s*:\s*([^\n,;]{2,40})""", RegexOption.IGNORE_CASE)
        private val NAMED_MERCHANT = Regex("""\b(?:en|at)\s+([A-Z0-9][A-Z0-9 *&.'/-]{2,39}?)(?=\s+[a-záéíóú]|[,.;\n]|$)""")

        fun parse(text: String?): SharedExpense? {
            val clean = text?.take(MAX_TEXT)?.trim().orEmpty()
            if (clean.isEmpty()) return null
            val first = SYMBOL_FIRST.find(clean)
            val last = SYMBOL_LAST.find(clean)
            val (rawNumber, rawCurrency) = when {
                first != null -> first.groupValues[2] to first.groupValues[1]
                last != null -> last.groupValues[1] to last.groupValues[2]
                else -> null to null
            }
            val merchant = (LABELED_MERCHANT.find(clean) ?: NAMED_MERCHANT.find(clean))?.groupValues?.get(1)?.trim()?.takeIf { it.isNotEmpty() }
            return SharedExpense(rawNumber?.let(::number), rawCurrency?.let(::currency), merchant)
        }

        private fun currency(raw: String): String = when (raw.uppercase()) {
            "₡", "CRC", "COLONES" -> "CRC"
            else -> "USD"
        }

        /** Whichever separator comes last with one or two digits after it is the decimal one; the rest group thousands. */
        private fun number(raw: String): BigDecimal? {
            val trimmed = raw.trimEnd('.', ',')
            val last = trimmed.lastIndexOfAny(charArrayOf('.', ','))
            val decimals = if (last >= 0) trimmed.length - last - 1 else 0
            val plain = if (last >= 0 && decimals in 1..2) trimmed.substring(0, last).filter(Char::isDigit) + "." + trimmed.substring(last + 1)
            else trimmed.filter(Char::isDigit)
            return plain.toBigDecimalOrNull()?.takeIf { it.signum() > 0 }
        }
    }
}
