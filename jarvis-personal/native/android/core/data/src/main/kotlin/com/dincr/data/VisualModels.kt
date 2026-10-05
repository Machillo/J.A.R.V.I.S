package com.dincr.data

import java.math.BigDecimal
import java.math.MathContext
import kotlin.math.floor
import kotlin.math.roundToInt

// Models behind the shared visual components (DESIGN.md → Data visualization).
// Visualize information; do not invent information: these types only describe values the caller
// already has. An unknown value stays unknown (never 0), a proportion exists only when the whole
// is known and positive, gaps in a series stay gaps, and a direction never decides by itself
// whether something is good or bad. iOS mirrors them in `DincrCore/VisualModels.swift`.

// region Composition (donut)

/** One part of a whole. `value == null` means unknown. Parts in different currencies are never added. */
data class CompositionItem(val id: String, val label: String, val value: BigDecimal?, val currency: String? = null)

/**
 * A whole split into parts, with each part's share only when it can be computed honestly.
 * Equal inputs give equal compositions, so a remembered selection survives recomposition.
 */
data class Composition(val items: List<CompositionItem>) {
    enum class Status {
        /** Every part is known and the total is positive: shares are exact. */
        COMPLETE,
        /** No parts. */
        EMPTY,
        /** Every part is known and they add up to zero: there is nothing to divide. */
        ZERO_TOTAL,
        /** Some parts are unknown: the known ones are listed, but no total or share is shown. */
        PARTIAL,
        /**
         * A negative part, or parts in different currencies (or only some with a currency): not a
         * composition. Nothing is drawn or totalled; the reason is shown in words.
         */
        INVALID,
    }

    /** [share] is value / total, only when [status] is [Status.COMPLETE]. */
    data class Segment(val id: String, val label: String, val value: BigDecimal, val share: Double?)

    val status: Status
    /** Parts with a known value, in the caller's order. */
    val segments: List<Segment>
    /** Parts whose value is unknown: listed as "no data", never drawn as 0. */
    val unknown: List<CompositionItem> = items.filter { it.value == null }
    /** Sum of the parts, only when [status] is [Status.COMPLETE]. */
    val total: BigDecimal?
    /** The parts' currency when they carry one; every amount is shown in it, never in another. */
    val currency: String?

    init {
        val known = items.mapNotNull { item -> item.value?.let { item to it } }
        val sum = known.fold(BigDecimal.ZERO) { acc, (_, value) -> acc + value }
        val currencies = items.mapNotNull { it.currency }.toSet()
        val someWithoutCurrency = currencies.isNotEmpty() && items.any { it.currency == null }
        currency = if (currencies.size == 1 && !someWithoutCurrency) currencies.first() else null
        status = when {
            items.isEmpty() -> Status.EMPTY
            known.any { it.second.signum() < 0 } || currencies.size > 1 || someWithoutCurrency -> Status.INVALID
            unknown.isNotEmpty() -> Status.PARTIAL
            sum.signum() == 0 -> Status.ZERO_TOTAL
            else -> Status.COMPLETE
        }
        total = if (status == Status.COMPLETE) sum else null
        segments = if (status == Status.INVALID) emptyList() else known.map { (item, value) ->
            Segment(item.id, item.label, value, if (status == Status.COMPLETE) value.divide(sum, MathContext.DECIMAL64).toDouble() else null)
        }
    }

    /** Whether the parts can be drawn as a donut: only an exact composition is. */
    val isDrawable: Boolean get() = status == Status.COMPLETE

    fun segment(id: String?): Segment? = segments.firstOrNull { it.id == id }

    /** The segment at a position around the circle (0 = start, 1 = full turn), for taps. */
    fun segmentAtFraction(fraction: Double): Segment? {
        if (!isDrawable || fraction < 0 || fraction > 1) return null
        var end = 0.0
        for (segment in segments) {
            val share = segment.share ?: continue
            if (share <= 0) continue   // a zero part has no arc to tap
            end += share
            if (fraction <= end) return segment
        }
        return segments.lastOrNull { (it.share ?: 0.0) > 0 }
    }

    companion object {
        /**
         * Position around a ring (0 at the top, clockwise, as the parts are drawn) of a tap at
         * ([dx], [dy]) from the ring's center, or null when it is in the hole or beyond the ring.
         */
        fun ringFraction(dx: Double, dy: Double, radius: Double, innerRatio: Double = 0.55): Double? {
            val distance = kotlin.math.hypot(dx, dy)
            if (radius <= 0 || distance < radius * innerRatio || distance > radius) return null
            val degrees = (kotlin.math.atan2(dy, dx) * 180 / Math.PI + 90 + 360) % 360
            return degrees / 360
        }
    }

    /** "Tarjeta: ₡120.000, 48 %" / "Préstamo: sin dato" — one line per part, for TalkBack and the legend. */
    fun spokenParts(format: MoneyFormat, language: AppLanguage = AppLanguage.current()): List<String> =
        segments.map { segment ->
            "${segment.label}: ${format.spoken(segment.value, language = language, currencyOverride = currency)}" +
                (segment.share?.let { ", ${VisualText.percent(it)}" } ?: "")
        } + unknown.map { "${it.label}: ${VisualText.noData(language)}" }
}

// endregion

// region Trend (line chart, sparkline)

/** One period of a series. [period] sorts chronologically ("2026-09"); `value == null` means no data. */
data class TrendPoint(val period: String, val label: String, val value: BigDecimal?)

/** A period that has a value: what a line can be drawn through. */
data class KnownPoint(val period: String, val label: String, val value: BigDecimal)

/**
 * A series in chronological order. Missing periods are never filled in: a period without data is
 * a gap, and the line is drawn only between consecutive known points. Equal inputs give equal
 * series, so a remembered selection survives recomposition.
 */
data class TrendSeries(private val input: List<TrendPoint>) {
    /** Sorted by period; when a period repeats, the first one given is kept. */
    val points: List<TrendPoint> = input.distinctBy { it.period }.sortedBy { it.period }

    val knownPoints: List<TrendPoint> get() = points.filter { it.value != null }

    /** A trend needs at least two known values. */
    val hasTrend: Boolean get() = knownPoints.size >= 2

    /** Runs of consecutive known points: each run is drawn as one line, so a gap stays a gap. */
    val runs: List<List<KnownPoint>>
        get() {
            val runs = mutableListOf<List<KnownPoint>>()
            var current = mutableListOf<KnownPoint>()
            for (point in points) {
                val value = point.value
                if (value != null) {
                    current.add(KnownPoint(point.period, point.label, value))
                } else if (current.isNotEmpty()) {
                    runs.add(current); current = mutableListOf()
                }
            }
            if (current.isNotEmpty()) runs.add(current)
            return runs
        }

    /** Lowest and highest known values (negative values are allowed), for scaling. */
    val range: ClosedRange<BigDecimal>?
        get() {
            val values = knownPoints.mapNotNull { it.value }
            val low = values.minOrNull() ?: return null
            return low..values.max()
        }

    /** Direction from the first to the last known value. */
    val direction: TrendDirection
        get() = TrendDirection.between(knownPoints.firstOrNull()?.value, if (hasTrend) knownPoints.last().value else null)

    /** "ene: ₡100.000; feb: sin dato; mar: ₡80.000" — every period, gaps included. */
    fun spokenPoints(format: MoneyFormat, language: AppLanguage = AppLanguage.current()): String =
        points.joinToString("; ") { point ->
            "${point.label}: ${point.value?.let { format.spoken(it, language = language) } ?: VisualText.noData(language)}"
        }

    /** One-sentence summary for a sparkline: first and last values, direction, periods without data. */
    fun spokenSummary(format: MoneyFormat, language: AppLanguage = AppLanguage.current()): String {
        val known = knownPoints
        val first = known.firstOrNull() ?: return VisualText.noData(language)
        val firstValue = format.spoken(first.value!!, language = language)
        if (!hasTrend) {
            return language.pick("Solo un dato: ${first.label}, $firstValue. Todavía no hay tendencia.",
                "Only one value: ${first.label}, $firstValue. No trend yet.")
        }
        val last = known.last()
        val lastValue = format.spoken(last.value!!, language = language)
        val change = VisualText.direction(direction, language)
        var text = language.pick("De $firstValue en ${first.label} a $lastValue en ${last.label}: $change",
            "From $firstValue in ${first.label} to $lastValue in ${last.label}: $change")
        val gaps = points.size - known.size
        if (gaps > 0) text += language.pick(". $gaps sin dato", ". $gaps without data")
        return text
    }
}

// endregion

// region Direction and its meaning

/**
 * Which way a value moved. It says nothing about whether that is good: debt going down is good,
 * savings going down is not. The caller gives the meaning ([TrendMeaning]).
 */
enum class TrendDirection {
    UP, DOWN, FLAT,
    /** Fewer than two known values: there is nothing to compare. */
    INSUFFICIENT;

    companion object {
        fun between(previous: BigDecimal?, current: BigDecimal?): TrendDirection {
            if (previous == null || current == null) return INSUFFICIENT
            val order = current.compareTo(previous)
            return if (order > 0) UP else if (order < 0) DOWN else FLAT
        }
    }
}

/** What a movement means for the user, decided by the caller for that metric. */
enum class TrendMeaning { FAVORABLE, UNFAVORABLE, NEUTRAL }

/** A direction plus the meaning the caller gives it. The tone comes only from the meaning. */
data class TrendSignal(val direction: TrendDirection, val meaning: TrendMeaning) {
    enum class Tone { POSITIVE, ATTENTION, NEUTRAL, UNAVAILABLE }

    val tone: Tone
        get() = if (direction == TrendDirection.INSUFFICIENT) Tone.UNAVAILABLE else when (meaning) {
            TrendMeaning.FAVORABLE -> Tone.POSITIVE
            TrendMeaning.UNFAVORABLE -> Tone.ATTENTION
            TrendMeaning.NEUTRAL -> Tone.NEUTRAL
        }

    /** "Deuda: baja, buena señal" — what changed and what it means, without the picture. */
    fun spoken(label: String, language: AppLanguage = AppLanguage.current()): String {
        val meaningText = if (direction == TrendDirection.INSUFFICIENT) "" else VisualText.meaning(meaning, language)
        val change = listOf(VisualText.direction(direction, language), meaningText).filter { it.isNotEmpty() }.joinToString(", ")
        return listOf(label, change).filter { it.isNotEmpty() }.joinToString(": ")
    }
}

// endregion

// region Progress

/**
 * Progress toward a target. [fraction] exists only when both values are known, the current value
 * is not negative and the target is positive: no division by zero and no unknown shown as 0 %.
 * Above 100 % is kept ([isOver]); the bar itself is clamped.
 */
class ProgressValue private constructor(val status: Status, val fraction: Double?) {
    enum class Status { VALID, UNKNOWN, INVALID_TARGET, INVALID_CURRENT }

    /** The bar's fill, 0..1. */
    val displayFraction: Double? get() = fraction?.coerceIn(0.0, 1.0)
    val isOver: Boolean get() = (fraction ?: 0.0) > 1
    val isComplete: Boolean get() = (fraction ?: 0.0) >= 1
    /**
     * Whole percent rounded down, so 99.6 % never reads as done. A tiny tolerance keeps binary
     * floating point from turning 29 % into 28 %.
     */
    val percent: Int? get() = fraction?.let { floor(it * 100 + 1e-9).toInt() }

    companion object {
        fun of(current: BigDecimal?, target: BigDecimal?): ProgressValue = when {
            current == null || target == null -> ProgressValue(Status.UNKNOWN, null)
            target.signum() <= 0 -> ProgressValue(Status.INVALID_TARGET, null)
            current.signum() < 0 -> ProgressValue(Status.INVALID_CURRENT, null)
            else -> ProgressValue(Status.VALID, current.divide(target, MathContext.DECIMAL64).toDouble())
        }

        /** A known ratio given directly (for example a backend percentage / 100). */
        fun ofFraction(fraction: Double?): ProgressValue = when {
            fraction == null -> ProgressValue(Status.UNKNOWN, null)
            fraction.isNaN() || fraction.isInfinite() || fraction < 0 -> ProgressValue(Status.INVALID_CURRENT, null)
            else -> ProgressValue(Status.VALID, fraction)
        }
    }
}

// endregion

/** Shared wording for the visual components. */
object VisualText {
    fun noData(language: AppLanguage = AppLanguage.current()) = language.pick("sin dato", "no data")

    /** "48 %": whole percent, rounded to nearest (a share, not a completion). */
    fun percent(share: Double) = "${(share * 100).roundToInt()} %"

    fun direction(direction: TrendDirection, language: AppLanguage = AppLanguage.current()) = when (direction) {
        TrendDirection.UP -> language.pick("sube", "up")
        TrendDirection.DOWN -> language.pick("baja", "down")
        TrendDirection.FLAT -> language.pick("estable", "steady")
        TrendDirection.INSUFFICIENT -> language.pick("sin comparación", "no comparison")
    }

    fun meaning(meaning: TrendMeaning, language: AppLanguage = AppLanguage.current()) = when (meaning) {
        TrendMeaning.FAVORABLE -> language.pick("buena señal", "good sign")
        TrendMeaning.UNFAVORABLE -> language.pick("merece atención", "worth attention")
        TrendMeaning.NEUTRAL -> ""
    }
}
