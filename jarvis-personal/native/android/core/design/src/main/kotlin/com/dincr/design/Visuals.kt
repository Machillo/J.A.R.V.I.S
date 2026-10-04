package com.dincr.design

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.East
import androidx.compose.material.icons.rounded.NorthEast
import androidx.compose.material.icons.rounded.PieChart
import androidx.compose.material.icons.rounded.Remove
import androidx.compose.material.icons.rounded.SouthEast
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.dincr.data.AppLanguage
import com.dincr.data.Composition
import com.dincr.data.ProgressValue
import com.dincr.data.TrendDirection
import com.dincr.data.TrendMeaning
import com.dincr.data.TrendSeries
import com.dincr.data.TrendSignal
import com.dincr.data.VisualText
import com.dincr.design.generated.DincrRadius
import com.dincr.design.generated.DincrSpacing
import kotlin.math.max
import kotlin.math.min

// Shared visual components (DESIGN.md → Data visualization). They draw what the models in
// `com.dincr.data.VisualModels` describe and never compute or fill in financial values: unknown
// stays "no data", a gap stays a gap, a proportion appears only when it is exact. Every component
// is readable without the picture (TalkBack gets the values, not just a title). iOS draws the same
// components in `DincrDesign/Components/Visuals.swift`.

// region Donut

/**
 * Composition of a whole: one hue in steps (no rainbow; parts are told apart by the legend's direct
 * labels, never by color alone), a center label, and a legend whose rows select a part. When the
 * parts can't form an exact whole, the donut is not drawn and the legend still lists every known
 * part and every unknown one as "no data". Amounts are shown in the parts' currency.
 * `showsTotal = false` when the caller has its own total and the sum of the parts must not be shown
 * as one (the center then shows only a selected part).
 */
@Composable
fun CompositionDonut(
    title: String, composition: Composition, color: Color = Dincr.colors.chartExpense, showsLegend: Boolean = true, showsTotal: Boolean = true,
) {
    var selectedId by remember(composition) { mutableStateOf<String?>(null) }
    val format = Dincr.money
    val parts = composition.spokenParts(format)
    fun shade(index: Int, id: String): Color =
        if (selectedId != null) color.copy(alpha = if (id == selectedId) 1f else 0.4f) else color.copy(alpha = visualShade(index))

    Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
        if (composition.isDrawable) {
            Box(Modifier.fillMaxWidth().height(200.dp), contentAlignment = Alignment.Center) {
                Canvas(
                    Modifier.size(200.dp)
                        .pointerInputTap(composition) { offset, size ->
                            val fraction = Composition.ringFraction(
                                (offset.x - size.width / 2).toDouble(), (offset.y - size.height / 2).toDouble(), (min(size.width, size.height) / 2).toDouble(),
                            ) ?: return@pointerInputTap
                            val id = composition.segmentAtFraction(fraction)?.id
                            selectedId = if (id == selectedId) null else id
                        }
                        // With a legend, its rows read every part; without one, the chart does.
                        .clearAndSetSemantics { if (!showsLegend) contentDescription = "$title. ${parts.joinToString("; ")}" },
                ) {
                    val stroke = size.minDimension * 0.19f
                    val inset = stroke / 2
                    var start = -90f
                    composition.segments.forEachIndexed { index, segment ->
                        val sweep = ((segment.share ?: 0.0) * 360).toFloat()
                        if (sweep <= 0f) return@forEachIndexed   // a zero part has no arc
                        val gap = if (composition.segments.size > 1) min(1.5f, sweep / 4) else 0f
                        drawArc(
                            color = shade(index, segment.id), startAngle = start + gap / 2, sweepAngle = sweep - gap, useCenter = false,
                            topLeft = Offset(inset, inset), size = Size(size.width - stroke, size.height - stroke), style = Stroke(stroke),
                        )
                        start += sweep
                    }
                }
                val selected = composition.segment(selectedId)
                Column(Modifier.widthIn(max = 110.dp).clearAndSetSemantics { }, horizontalAlignment = Alignment.CenterHorizontally) {
                    if (selected != null) {
                        Text(selected.label, style = MaterialTheme.typography.labelMedium, color = Dincr.colors.text2, textAlign = TextAlign.Center, maxLines = 2)
                        MoneyText(selected.value, style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold), currency = composition.currency)
                        selected.share?.let { Text(VisualText.percent(it), style = MaterialTheme.typography.labelMedium, color = Dincr.colors.text2) }
                    } else if (showsTotal) composition.total?.let {
                        Text(AppLanguage.current().pick("Total", "Total"), style = MaterialTheme.typography.labelMedium, color = Dincr.colors.text2)
                        MoneyText(it, style = MaterialTheme.typography.titleMedium.copy(fontWeight = FontWeight.SemiBold), currency = composition.currency)
                    }
                }
            }
        } else {
            VisualNotice(compositionNotice(composition.status), title)
        }
        if (showsLegend) {
            Column {
                composition.segments.forEachIndexed { index, segment ->
                    val selectable = if (composition.isDrawable) Modifier.selectable(
                        selected = selectedId == segment.id, role = Role.Button,
                        onClick = { selectedId = if (selectedId == segment.id) null else segment.id },
                    ) else Modifier
                    Row(
                        Modifier.fillMaxWidth().heightIn(min = 48.dp).then(selectable).semantics(mergeDescendants = true) { contentDescription = parts[index] },
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        if (composition.isDrawable) Box(Modifier.size(10.dp).background(shade(index, segment.id), CircleShape))
                        Text(segment.label, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text,
                            modifier = Modifier.weight(1f).padding(start = if (composition.isDrawable) DincrSpacing.s3 else 0.dp, end = DincrSpacing.s2))
                        Column(horizontalAlignment = Alignment.End) {
                            MoneyText(segment.value, style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold), currency = composition.currency)
                            segment.share?.let { Text(VisualText.percent(it), style = MaterialTheme.typography.labelMedium, color = Dincr.colors.text2) }
                        }
                    }
                }
                composition.unknown.forEach { item ->
                    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).semantics(mergeDescendants = true) { }, verticalAlignment = Alignment.CenterVertically) {
                        Text(item.label, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text, modifier = Modifier.weight(1f))
                        Text(VisualText.noData().replaceFirstChar { it.uppercase() }, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.textMuted)
                    }
                }
            }
        }
    }
}

/** Opacity steps for the parts of one hue: strong first, never fainter than readable. */
internal fun visualShade(index: Int): Float = max(0.3f, 1f - index * 0.17f)

private fun compositionNotice(status: Composition.Status): String {
    val language = AppLanguage.current()
    return when (status) {
        Composition.Status.EMPTY -> language.pick("Todavía no hay datos.", "No data yet.")
        Composition.Status.ZERO_TOTAL -> language.pick("Todo suma cero: no hay partes que comparar.", "Everything adds up to zero: nothing to compare.")
        Composition.Status.PARTIAL -> language.pick("Faltan datos de algunas partes, así que no mostramos proporciones.", "Some parts have no data, so proportions aren’t shown.")
        Composition.Status.INVALID -> language.pick("Estos valores no se pueden sumar en un solo total.", "These values can’t be added into one total.")
        Composition.Status.COMPLETE -> ""
    }
}

// endregion

// region Line

/**
 * Evolution over time (DESIGN_SYSTEM.md §8: 2 dp line, baseline at 0, markers on selection). Each
 * run of consecutive known periods is one line; a period without data stays on the axis as a gap,
 * and a value isolated between gaps keeps a small marker so it is never hidden. Fewer than two
 * known values show a notice instead of a trend. Tapping selects the nearest period and shows its
 * value below.
 */
@Composable
fun TrendLineChart(title: String, series: TrendSeries, color: Color = Dincr.colors.chartExpense) {
    val format = Dincr.money
    val c = Dincr.colors
    var selectedPeriod by remember(series) { mutableStateOf<String?>(null) }
    Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
        if (!series.hasTrend) {
            VisualNotice(AppLanguage.current().pick("Todavía no hay suficientes datos para ver una tendencia.", "Not enough data yet to show a trend."), title)
            series.knownPoints.firstOrNull()?.let { only ->
                Row(Modifier.fillMaxWidth().semantics(mergeDescendants = true) { }) {
                    Text(only.label, style = MaterialTheme.typography.bodyMedium, color = c.text2, modifier = Modifier.weight(1f))
                    MoneyText(only.value, style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold))
                }
            }
            return@Column
        }
        val range = series.range ?: return@Column
        // The y domain always includes 0, so the baseline is real and a small change is not magnified.
        val low = minOf(range.start.toDouble(), 0.0)
        val high = maxOf(range.endInclusive.toDouble(), 0.0)
        val count = series.points.size
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.width(AxisWidth).height(180.dp).clearAndSetSemantics { }, verticalArrangement = Arrangement.SpaceBetween) {
                Text(compactAxis(high), style = MaterialTheme.typography.labelSmall, color = c.textMuted)
                Text(compactAxis(low), style = MaterialTheme.typography.labelSmall, color = c.textMuted)
            }
            Canvas(
                Modifier.weight(1f).height(180.dp).padding(start = DincrSpacing.s2)
                    .pointerInputTap(series) { offset, size ->
                        // Each period owns an equal band; its point sits at the band's center, under its label.
                        val index = (offset.x / (size.width / count)).toInt().coerceIn(0, count - 1)
                        val period = series.points[index].period
                        selectedPeriod = if (period == selectedPeriod) null else period
                    }
                    .clearAndSetSemantics { contentDescription = "$title. ${series.spokenPoints(format)}" },
            ) {
                val span = (high - low).takeIf { it > 0 }
                val band = size.width / count
                fun x(period: String) = (series.points.indexOfFirst { it.period == period } + 0.5f) * band
                fun y(value: Double) = if (span == null) size.height / 2 else size.height - ((value - low) / span * size.height).toFloat()
                for (fraction in listOf(0f, 0.5f, 1f)) {
                    drawLine(c.line, Offset(0f, size.height * fraction), Offset(size.width, size.height * fraction), strokeWidth = 1.dp.toPx())
                }
                drawLine(c.lineStrong, Offset(0f, y(0.0)), Offset(size.width, y(0.0)), strokeWidth = 1.dp.toPx())
                selectedPeriod?.let { period -> if (series.points.first { it.period == period }.value != null) drawLine(c.line, Offset(x(period), 0f), Offset(x(period), size.height), strokeWidth = 1.dp.toPx()) }
                series.runs.forEach { run ->
                    val path = Path()
                    run.forEachIndexed { index, point ->
                        val p = Offset(x(point.period), y(point.value.toDouble()))
                        if (index == 0) path.moveTo(p.x, p.y) else path.lineTo(p.x, p.y)
                    }
                    if (run.size > 1) drawPath(path, color, style = Stroke(2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
                    run.forEach { point ->
                        val center = Offset(x(point.period), y(point.value.toDouble()))
                        if (point.period == selectedPeriod) {
                            drawCircle(c.surface, 7.dp.toPx(), center)
                            drawCircle(color, 5.dp.toPx(), center)
                        } else if (run.size == 1) {
                            drawCircle(color, 3.dp.toPx(), center)
                        }
                    }
                }
            }
        }
        // Same start as the plot (axis column + its gap), so each label sits under its band.
        Row(Modifier.fillMaxWidth().padding(start = AxisWidth + DincrSpacing.s2).clearAndSetSemantics { }) {
            series.points.forEach { point ->
                Text(point.label, style = MaterialTheme.typography.labelSmall, color = c.textMuted, textAlign = TextAlign.Center, modifier = Modifier.weight(1f), maxLines = 1)
            }
        }
        series.points.firstOrNull { it.period == selectedPeriod }?.let { point ->
            Row(Modifier.fillMaxWidth().semantics(mergeDescendants = true) { }) {
                Text(point.label, style = MaterialTheme.typography.bodyMedium, color = c.text2, modifier = Modifier.weight(1f))
                val value = point.value
                if (value != null) MoneyText(value, style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold))
                else Text(VisualText.noData().replaceFirstChar { it.uppercase() }, style = MaterialTheme.typography.bodyMedium, color = c.textMuted)
            }
        }
    }
}

/** Width of the y-axis labels column, shared by the plot and the period labels below it. */
private val AxisWidth = 40.dp

/** Short axis labels ("1.2M", "350k", "−80k"); the values themselves stay in the selection and TalkBack. */
internal fun compactAxis(value: Double): String {
    val sign = if (value < 0) "−" else ""
    val magnitude = kotlin.math.abs(value)
    return sign + when {
        magnitude >= 1_000_000 -> String.format(java.util.Locale.ROOT, "%.1fM", magnitude / 1_000_000)
        magnitude >= 1_000 -> "${(magnitude / 1_000).toInt()}k"
        else -> "${magnitude.toInt()}"
    }
}

// endregion

// region Sparkline

/**
 * A small trend for a card: no axes or legend, gaps kept, and a spoken summary (first and last
 * values, direction, periods without data). With fewer than two values it says so in text.
 */
@Composable
fun Sparkline(label: String, series: TrendSeries, color: Color = Dincr.colors.chartExpense) {
    val summary = series.spokenSummary(Dincr.money)
    val description = Modifier.clearAndSetSemantics { contentDescription = "$label. $summary" }
    val range = series.range
    if (!series.hasTrend || range == null) {
        Text(AppLanguage.current().pick("Sin tendencia todavía", "No trend yet"), style = MaterialTheme.typography.labelMedium, color = Dincr.colors.textMuted, modifier = description)
        return
    }
    Canvas(Modifier.fillMaxWidth().height(32.dp).then(description)) {
        val count = series.points.size
        val band = size.width / count
        fun x(period: String) = (series.points.indexOfFirst { it.period == period } + 0.5f) * band
        val low = range.start.toDouble()
        val span = (range.endInclusive.toDouble() - low).takeIf { it > 0 }
        val pad = 2.dp.toPx()
        fun y(value: Double) = if (span == null) size.height / 2 else size.height - pad - ((value - low) / span * (size.height - 2 * pad)).toFloat()
        series.runs.forEach { run ->
            val path = Path()
            run.forEachIndexed { index, point ->
                if (index == 0) path.moveTo(x(point.period), y(point.value.toDouble())) else path.lineTo(x(point.period), y(point.value.toDouble()))
            }
            if (run.size > 1) drawPath(path, color, style = Stroke(2.dp.toPx(), cap = StrokeCap.Round, join = StrokeJoin.Round))
            else drawCircle(color, 2.dp.toPx(), Offset(x(run.first().period), y(run.first().value.toDouble())))
        }
    }
}

// endregion

// region Trend indicator

/**
 * Which way something moved (arrow and word) and what the caller says it means (color and, when it
 * has one, a word: never color alone). The direction never picks the color: debt going down and
 * savings going down look different.
 */
@Composable
fun TrendIndicator(label: String, signal: TrendSignal) {
    val c = Dincr.colors
    val (foreground, fill) = when (signal.tone) {
        TrendSignal.Tone.POSITIVE -> c.positive to c.positiveContainer
        TrendSignal.Tone.ATTENTION -> c.warning to c.warningContainer
        TrendSignal.Tone.NEUTRAL -> c.text2 to c.surface2
        TrendSignal.Tone.UNAVAILABLE -> c.textMuted to c.surface2
    }
    val icon: ImageVector = when (signal.direction) {
        TrendDirection.UP -> Icons.Rounded.NorthEast
        TrendDirection.DOWN -> Icons.Rounded.SouthEast
        TrendDirection.FLAT -> Icons.Rounded.East
        TrendDirection.INSUFFICIENT -> Icons.Rounded.Remove
    }
    val spoken = signal.spoken(label)
    Row(
        Modifier.background(fill, CircleShape).padding(horizontal = DincrSpacing.s2, vertical = 3.dp).clearAndSetSemantics { contentDescription = spoken },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, contentDescription = null, tint = foreground, modifier = Modifier.size(14.dp))
        val direction = VisualText.direction(signal.direction).replaceFirstChar { it.uppercase() }
        val meaning = if (signal.direction == TrendDirection.INSUFFICIENT) "" else VisualText.meaning(signal.meaning)
        Text(if (meaning.isEmpty()) direction else "$direction · $meaning", style = MaterialTheme.typography.labelMedium.copy(fontWeight = FontWeight.SemiBold),
            color = foreground, modifier = Modifier.padding(start = DincrSpacing.s1))
    }
}

// endregion

// region Progress

/**
 * Progress from known values as a bar (no rings — DESIGN.md → Shapes). Unknown or invalid progress
 * shows "no data" in words, never an empty bar that would read as 0 %. Going past 100 % means what
 * the caller says: over a goal is good, over a budget is not. The caller shows the value in text;
 * the bar itself is not read by TalkBack.
 */
@Composable
fun DincrProgressBar(progress: ProgressValue, overMeaning: TrendMeaning = TrendMeaning.NEUTRAL) {
    val c = Dincr.colors
    val fraction = progress.displayFraction
    if (fraction == null) {
        Text(VisualText.noData().replaceFirstChar { it.uppercase() }, style = MaterialTheme.typography.labelMedium, color = c.textMuted)
        return
    }
    val fill = if (!progress.isOver) c.tint else when (overMeaning) {
        TrendMeaning.FAVORABLE -> c.positive
        TrendMeaning.UNFAVORABLE -> c.negative
        TrendMeaning.NEUTRAL -> c.tint
    }
    Box(Modifier.fillMaxWidth().height(8.dp).background(c.surface2, CircleShape).clearAndSetSemantics { }) {
        if (fraction > 0) Box(Modifier.fillMaxWidth(fraction.toFloat()).widthIn(min = 6.dp).height(8.dp).background(fill, CircleShape))
    }
}

// endregion

/** Why a chart isn't drawn, in words; TalkBack hears which chart it is about. */
@Composable
private fun VisualNotice(text: String, title: String) {
    Row(
        Modifier.fillMaxWidth().background(Dincr.colors.surface2, RoundedCornerShape(DincrRadius.md)).padding(DincrSpacing.s3)
            .clearAndSetSemantics { contentDescription = "$title. $text" },
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(Icons.Rounded.PieChart, contentDescription = null, tint = Dincr.colors.textMuted)
        Spacer(Modifier.width(DincrSpacing.s2))
        Text(text, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2)
    }
}

/** A tap with the position and the drawing size, for charts; restarts when [key] (the data) changes. */
private fun Modifier.pointerInputTap(key: Any?, onTap: (Offset, Size) -> Unit): Modifier =
    this.then(Modifier.pointerInput(key) {
        detectTapGestures { offset -> onTap(offset, Size(size.width.toFloat(), size.height.toFloat())) }
    })
