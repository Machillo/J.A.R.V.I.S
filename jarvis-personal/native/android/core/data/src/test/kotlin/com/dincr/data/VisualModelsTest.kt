package com.dincr.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.math.BigDecimal

/**
 * Visualize information; do not invent information (DESIGN.md → Data visualization).
 * The Swift twin is `VisualModelsTests`.
 */
class VisualModelsTest {
    private val format = MoneyFormat()
    private val es = AppLanguage.SPANISH
    private fun bd(value: Long) = BigDecimal.valueOf(value)
    private fun item(id: String, value: Long?, currency: String? = null) = CompositionItem(id, id.uppercase(), value?.let(::bd), currency)

    // region Composition

    @Test fun anEmptyCompositionHasNothingToDraw() {
        val composition = Composition(emptyList())
        assertEquals(Composition.Status.EMPTY, composition.status)
        assertFalse(composition.isDrawable)
        assertNull(composition.total)
        assertTrue(composition.segments.isEmpty())
    }

    @Test fun aSinglePartIsTheWhole() {
        val composition = Composition(listOf(item("card", 250_000)))
        assertEquals(Composition.Status.COMPLETE, composition.status)
        assertEquals(bd(250_000), composition.total)
        assertEquals(1.0, composition.segments.single().share!!, 0.0)
    }

    @Test fun sharesAreExactAndKeepTheCallersOrderAndValues() {
        val composition = Composition(listOf(item("a", 50), item("b", 150)))
        assertEquals(listOf("a", "b"), composition.segments.map { it.id })
        assertEquals(listOf(bd(50), bd(150)), composition.segments.map { it.value })
        assertEquals(listOf(0.25, 0.75), composition.segments.map { it.share })
        assertEquals(bd(200), composition.total)
    }

    @Test fun zeroTotalHasNoSharesButKeepsTheRealZeros() {
        val composition = Composition(listOf(item("a", 0), item("b", 0)))
        assertEquals(Composition.Status.ZERO_TOTAL, composition.status)
        assertFalse(composition.isDrawable)
        assertNull(composition.total)
        assertEquals(listOf(BigDecimal.ZERO, BigDecimal.ZERO), composition.segments.map { it.value })
        assertTrue(composition.segments.all { it.share == null })
    }

    @Test fun anUnknownPartIsNeverZeroAndBlocksSharesAndTotal() {
        val composition = Composition(listOf(CompositionItem("a", "Tarjeta", bd(100)), CompositionItem("b", "Préstamo", null)))
        assertEquals(Composition.Status.PARTIAL, composition.status)
        assertFalse(composition.isDrawable)
        assertNull(composition.total)
        assertEquals(listOf("a"), composition.segments.map { it.id })
        assertNull(composition.segments.single().share)
        assertEquals(listOf("b"), composition.unknown.map { it.id })
        val parts = composition.spokenParts(format, es)
        assertEquals("Préstamo: sin dato", parts.last())
        assertFalse(parts.joinToString().contains("%"))
    }

    @Test fun negativePartsOrMixedCurrenciesAreNotAComposition() {
        val negative = Composition(listOf(item("a", 100), item("b", -5)))
        assertEquals(Composition.Status.INVALID, negative.status)
        assertTrue(negative.segments.isEmpty())
        assertNull(negative.total)
        val mixed = Composition(listOf(item("a", 100, "CRC"), item("b", 100, "USD")))
        assertEquals(Composition.Status.INVALID, mixed.status)
        assertNull(mixed.total)
        val same = Composition(listOf(item("a", 100, "USD"), item("b", 300, "USD")))
        assertEquals(Composition.Status.COMPLETE, same.status)
        assertEquals(bd(400), same.total)
    }

    @Test fun selectionFindsTheSegmentUnderATapOrById() {
        val composition = Composition(listOf(item("a", 25), item("b", 75)))
        assertEquals("a", composition.segmentAtFraction(0.0)?.id)
        assertEquals("a", composition.segmentAtFraction(0.2)?.id)
        assertEquals("b", composition.segmentAtFraction(0.3)?.id)
        assertEquals("b", composition.segmentAtFraction(1.0)?.id)
        assertNull(composition.segmentAtFraction(1.2))
        assertEquals(0.75, composition.segment("b")?.share!!, 0.0)
        assertNull(composition.segment("missing"))
        assertNull(Composition(listOf(item("a", null))).segmentAtFraction(0.5))
    }

    /**
     * A tap on the ring maps to its position around the circle (0 at the top, clockwise); taps in
     * the hole or beyond the ring select nothing.
     */
    @Test fun aTapOnTheRingMapsToItsPosition() {
        assertEquals(0.0, Composition.ringFraction(0.0, -90.0, 100.0)!!, 0.0001)
        assertEquals(0.25, Composition.ringFraction(90.0, 0.0, 100.0)!!, 0.0001)
        assertEquals(0.5, Composition.ringFraction(0.0, 90.0, 100.0)!!, 0.0001)
        assertEquals(0.75, Composition.ringFraction(-90.0, 0.0, 100.0)!!, 0.0001)
        assertNull(Composition.ringFraction(10.0, 10.0, 100.0))    // the hole
        assertNull(Composition.ringFraction(120.0, 0.0, 100.0))    // outside
        assertNull(Composition.ringFraction(1.0, 1.0, 0.0))
        val composition = Composition(listOf(item("a", 25), item("b", 75)))
        assertEquals("a", composition.segmentAtFraction(Composition.ringFraction(90.0, 0.0, 100.0)!!)?.id)
        assertEquals("b", composition.segmentAtFraction(Composition.ringFraction(0.0, 90.0, 100.0)!!)?.id)
    }

    @Test fun spokenPartsCarryLabelValueAndShare() {
        val composition = Composition(listOf(CompositionItem("a", "Tarjeta", bd(30_000)), CompositionItem("b", "Préstamo", bd(90_000))))
        val parts = composition.spokenParts(format, es)
        assertEquals(2, parts.size)
        assertTrue(parts[0], parts[0].startsWith("Tarjeta: ") && parts[0].endsWith(", 25 %"))
        assertTrue(parts[1], parts[1].startsWith("Préstamo: ") && parts[1].endsWith(", 75 %"))
        // Formatting reads the values; it never changes them.
        assertEquals(listOf(bd(30_000), bd(90_000)), composition.segments.map { it.value })
    }

    // endregion

    // region Trend

    @Test fun anEmptySeriesHasNoTrend() {
        val series = TrendSeries(emptyList())
        assertFalse(series.hasTrend)
        assertTrue(series.runs.isEmpty())
        assertNull(series.range)
        assertEquals(TrendDirection.INSUFFICIENT, series.direction)
        assertEquals("sin dato", series.spokenSummary(format, es))
    }

    @Test fun aSingleValueIsNotATrend() {
        val series = TrendSeries(listOf(TrendPoint("2026-09", "set", bd(100))))
        assertFalse(series.hasTrend)
        assertEquals(TrendDirection.INSUFFICIENT, series.direction)
        assertTrue(series.spokenSummary(format, es).contains("Todavía no hay tendencia"))
    }

    @Test fun pointsAreSortedChronologicallyAndDuplicatesKeepTheFirst() {
        val series = TrendSeries(listOf(
            TrendPoint("2026-09", "set", bd(3)), TrendPoint("2026-07", "jul", bd(1)),
            TrendPoint("2026-08", "ago", bd(2)), TrendPoint("2026-07", "jul", bd(99)),
        ))
        assertEquals(listOf("2026-07", "2026-08", "2026-09"), series.points.map { it.period })
        assertEquals(bd(1), series.points.first().value)
    }

    @Test fun missingPeriodsStayGapsAndAreNeverZero() {
        val series = TrendSeries(listOf(
            TrendPoint("2026-06", "jun", bd(100)), TrendPoint("2026-07", "jul", null),
            TrendPoint("2026-08", "ago", bd(80)), TrendPoint("2026-09", "set", bd(90)),
        ))
        assertEquals(4, series.points.size)
        assertNull(series.points[1].value)
        assertEquals(listOf(listOf("2026-06"), listOf("2026-08", "2026-09")), series.runs.map { run -> run.map { it.period } })
        assertEquals(listOf(bd(100), bd(80), bd(90)), series.runs.flatten().map { it.value })   // only real values are drawn
        assertEquals(bd(80)..bd(100), series.range)
        assertTrue(series.spokenPoints(format, es).contains("jul: sin dato"))
        assertTrue(series.spokenSummary(format, es).endsWith("1 sin dato"))
    }

    @Test fun negativeValuesAreAllowedInASeries() {
        val series = TrendSeries(listOf(TrendPoint("2026-08", "ago", bd(-50)), TrendPoint("2026-09", "set", bd(20))))
        assertEquals(bd(-50)..bd(20), series.range)
        assertEquals(TrendDirection.UP, series.direction)
    }

    // endregion

    // region Direction and meaning

    @Test fun directionComparesValuesOnly() {
        assertEquals(TrendDirection.UP, TrendDirection.between(bd(10), bd(20)))
        assertEquals(TrendDirection.DOWN, TrendDirection.between(bd(20), bd(10)))
        assertEquals(TrendDirection.FLAT, TrendDirection.between(bd(10), BigDecimal("10.00")))
        assertEquals(TrendDirection.INSUFFICIENT, TrendDirection.between(null, bd(10)))
        assertEquals(TrendDirection.INSUFFICIENT, TrendDirection.between(bd(10), null))
    }

    /** Debt going down is good and savings going down is not: the tone comes only from the meaning. */
    @Test fun directionNeverImpliesMeaning() {
        val debtDown = TrendSignal(TrendDirection.between(bd(500), bd(400)), TrendMeaning.FAVORABLE)
        val savingsDown = TrendSignal(TrendDirection.between(bd(500), bd(400)), TrendMeaning.UNFAVORABLE)
        assertEquals(debtDown.direction, savingsDown.direction)
        assertEquals(TrendSignal.Tone.POSITIVE, debtDown.tone)
        assertEquals(TrendSignal.Tone.ATTENTION, savingsDown.tone)
        for (direction in listOf(TrendDirection.UP, TrendDirection.DOWN, TrendDirection.FLAT)) {
            assertEquals(TrendSignal.Tone.POSITIVE, TrendSignal(direction, TrendMeaning.FAVORABLE).tone)
            assertEquals(TrendSignal.Tone.ATTENTION, TrendSignal(direction, TrendMeaning.UNFAVORABLE).tone)
            assertEquals(TrendSignal.Tone.NEUTRAL, TrendSignal(direction, TrendMeaning.NEUTRAL).tone)
        }
        for (meaning in TrendMeaning.entries) {
            assertEquals(TrendSignal.Tone.UNAVAILABLE, TrendSignal(TrendDirection.INSUFFICIENT, meaning).tone)
        }
    }

    @Test fun aSignalIsReadableWithoutThePicture() {
        assertEquals("Deuda: baja, buena señal", TrendSignal(TrendDirection.DOWN, TrendMeaning.FAVORABLE).spoken("Deuda", es))
        assertEquals("Ahorro: baja, merece atención", TrendSignal(TrendDirection.DOWN, TrendMeaning.UNFAVORABLE).spoken("Ahorro", es))
        assertEquals("Gastos: sube", TrendSignal(TrendDirection.UP, TrendMeaning.NEUTRAL).spoken("Gastos", es))
        assertEquals("Deuda: sin comparación", TrendSignal(TrendDirection.INSUFFICIENT, TrendMeaning.FAVORABLE).spoken("Deuda", es))
    }

    // endregion

    // region Progress

    @Test fun progressHandlesZeroNormalCompleteAndOver() {
        assertEquals(0.0, ProgressValue.of(bd(0), bd(100)).fraction!!, 0.0)
        assertEquals(0, ProgressValue.of(bd(0), bd(100)).percent)
        assertEquals(0.4, ProgressValue.of(bd(40), bd(100)).displayFraction!!, 0.0)
        val done = ProgressValue.of(bd(100), bd(100))
        assertTrue(done.isComplete && !done.isOver && done.percent == 100)
        val over = ProgressValue.of(bd(150), bd(100))
        assertTrue(over.isOver)
        assertEquals(1.0, over.displayFraction!!, 0.0)
        assertEquals(150, over.percent)
    }

    @Test fun progressNeverDividesByZeroOrShowsUnknownAsZero() {
        assertEquals(ProgressValue.Status.INVALID_TARGET, ProgressValue.of(bd(50), bd(0)).status)
        assertNull(ProgressValue.of(bd(50), bd(-10)).fraction)
        assertEquals(ProgressValue.Status.UNKNOWN, ProgressValue.of(null, bd(100)).status)
        assertNull(ProgressValue.of(bd(50), null).percent)
        assertEquals(ProgressValue.Status.INVALID_CURRENT, ProgressValue.of(bd(-1), bd(100)).status)
        assertNull(ProgressValue.ofFraction(null).displayFraction)
        assertNull(ProgressValue.ofFraction(Double.NaN).fraction)
        assertEquals(50, ProgressValue.ofFraction(0.5).percent)
    }

    @Test fun almostDoneNeverReadsAsDone() {
        val almost = ProgressValue.of(bd(996), bd(1000))
        assertEquals(99, almost.percent)
        assertFalse(almost.isComplete)
    }

    // endregion
}
