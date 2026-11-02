package com.dincr.data

import java.math.BigDecimal
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * The mail notice correction reads the decimal the keyboard offers ("453,84" or "453.84") with
 * either profile number format, and refuses ambiguous or mixed text instead of guessing.
 * iOS twin: `EmailMonitorTests.theCorrectionSheetReadsTheDecimalTheKeyboardOffers`.
 */
class CorrectionInputTest {
    private val formats = MoneyFormat.Separators.entries

    private fun same(expected: String, actual: BigDecimal?, label: String) =
        assertEquals(label, 0, BigDecimal(expected).compareTo(actual ?: error("$label was refused")))

    @Test fun theKeyboardsDecimalWorksWithEitherProfileFormat() {
        formats.forEach { f ->
            same("453.84", CorrectionInput.rate("453,84", f), "rate 453,84 $f")
            same("453.84", CorrectionInput.rate("453.84", f), "rate 453.84 $f")
            same("507.5", CorrectionInput.rate("507,5", f), "rate 507,5 $f")
            same("507.123456", CorrectionInput.rate("507.123456", f), "rate 507.123456 $f")
            same("9.99", CorrectionInput.amount("9,99", f), "amount 9,99 $f")
            same("9.99", CorrectionInput.amount("9.99", f), "amount 9.99 $f")
        }
    }

    @Test fun theProfilesOwnFormatKeepsItsMeaning() {
        same("100000", CorrectionInput.amount("100.000", MoneyFormat.Separators.DOT_COMMA), "100.000 dot_comma")
        same("1000", CorrectionInput.amount("1,000", MoneyFormat.Separators.COMMA_DOT), "1,000 comma_dot")
    }

    @Test fun ambiguousOrMixedTextIsRefusedNeverGuessed() {
        assertNull(CorrectionInput.rate("453,840", MoneyFormat.Separators.COMMA_DOT))
        assertNull(CorrectionInput.rate("453.840", MoneyFormat.Separators.DOT_COMMA))
        listOf("1.234,5,6", "1,2,3", "12,34,567", "0,0000001", "0", "", "-1", "1e3", "abc").forEach { bad ->
            formats.forEach { f -> assertNull("$bad $f", CorrectionInput.rate(bad, f)) }
        }
        // With at most 2 decimals, the last separator of a mixed amount can only be the decimal.
        same("1234.56", CorrectionInput.amount("1.234,56", MoneyFormat.Separators.COMMA_DOT), "mixed comma_dot")
        same("1234.56", CorrectionInput.amount("1,234.56", MoneyFormat.Separators.DOT_COMMA), "mixed dot_comma")
    }

    @Test fun everyAmountReadsEitherSeparatorInAnyProfile() {
        // The new installment and every other money field: "." or ",", in any profile, one meaning.
        val cases = listOf(
            "47500,50" to "47500.5", "47500.50" to "47500.5", "1,5" to "1.5", "1.5" to "1.5",
            "18.450" to "18450", "18,450" to "18450", "1.000.000" to "1000000", "1,000,000" to "1000000",
            "18.450,75" to "18450.75", "18,450.75" to "18450.75",
        )
        formats.forEach { f ->
            cases.forEach { (text, expected) ->
                same(expected, AmountInput.parse(text, f), "$text $f")
                same(expected, AmountInput.parseZeroOrMore(text, f), "$text $f")
            }
            listOf("1,234,56", "1.5.2", "1,2.3", "1.234,567", "12,345.6.7").forEach { assertNull("$it $f", AmountInput.parse(it, f)) }
            same("12.5", CorrectionInput.interest("12,5", f), "interest $f")
            same("12.5", CorrectionInput.interest("12.5", f), "interest $f")
        }
        // `ExchangeRateInput` alone stays strict; the fields read rates through `CorrectionInput.rate`.
        assertNull(ExchangeRateInput.parse("453,84", MoneyFormat.Separators.COMMA_DOT))
    }

    /** Plan → Ingresos y base: "2390,79" typed on a comma_dot profile is 2390.79, never refused. */
    @Test fun declaredProfileAmountsAcceptTheKeyboardsDecimal() {
        val cd = MoneyFormat.Separators.COMMA_DOT
        assertEquals(0, BigDecimal("2390.79").compareTo(CorrectionInput.amountZeroOrMore("2390,79", cd)))
        assertEquals(0, BigDecimal("18450").compareTo(CorrectionInput.amountZeroOrMore("18,450", cd)))
        assertEquals(0, BigDecimal.ZERO.compareTo(CorrectionInput.amountZeroOrMore("0", cd)))
        assertEquals(0, BigDecimal("1234.5").compareTo(CorrectionInput.amountZeroOrMore("1.234,5", cd)))
        assertNull(CorrectionInput.amountZeroOrMore("12,3456", cd))
    }
}
