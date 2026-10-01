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
        assertNull(CorrectionInput.amount("1.234,56", MoneyFormat.Separators.COMMA_DOT))
        assertNull(CorrectionInput.amount("1,234.56", MoneyFormat.Separators.DOT_COMMA))
    }

    @Test fun theStrictParsersOfOtherFieldsAreUnchanged() {
        // The reported failure, kept on purpose for every field outside the correction sheet.
        assertNull(ExchangeRateInput.parse("453,84", MoneyFormat.Separators.COMMA_DOT))
        assertNull(AmountInput.parse("9,99", MoneyFormat.Separators.COMMA_DOT))
    }
}
