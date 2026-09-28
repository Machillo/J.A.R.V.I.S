package com.dincr.design

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Error
import androidx.compose.material.icons.rounded.Info
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.dincr.data.AppLanguage
import com.dincr.data.MoneyFormat
import com.dincr.data.MovementKind
import com.dincr.design.generated.DincrRadius
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal

/** Tabular digits for every amount. */
val TabularNums = TextStyle(fontFeatureSettings = "tnum")

/** Card surface: tonal, no shadow (DESIGN.md → Elevation & Depth). */
@Composable
fun DincrCard(modifier: Modifier = Modifier, content: @Composable () -> Unit) {
    Box(
        modifier
            .fillMaxWidth()
            .background(Dincr.colors.surface, RoundedCornerShape(DincrRadius.lg))
            .padding(DincrSpacing.s4),
    ) { content() }
}

/** An amount with a sign for movements, tabular digits and a spoken description. Unknown → "—". */
@Composable
fun MoneyText(amount: BigDecimal?, modifier: Modifier = Modifier, sign: MoneyFormat.Sign = MoneyFormat.Sign.NONE, style: TextStyle = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight.SemiBold), currency: String? = null) {
    val format = Dincr.money
    val spoken = amount?.let { format.spoken(it, sign, currencyOverride = currency) } ?: AppLanguage.current().pick("sin dato", "no data")
    Text(
        text = amount?.let { format.format(it, sign, currency) } ?: "—",
        style = style.merge(TabularNums),
        color = if (sign == MoneyFormat.Sign.INCOME) Dincr.colors.positive else Dincr.colors.text,
        maxLines = 1,
        modifier = modifier.semantics { contentDescription = spoken },
    )
}

/** DESIGN.md → Money row. Read-only rows show a lock, never a disabled look. */
@Composable
fun MoneyRow(title: String, subtitle: String, amount: BigDecimal, kind: MovementKind, icon: ImageVector, readOnly: Boolean, modifier: Modifier = Modifier, currency: String? = null) {
    val colors = Dincr.colors
    Row(modifier.fillMaxWidth().heightIn(min = 56.dp).padding(vertical = DincrSpacing.s2), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(40.dp).background(colors.surface2, CircleShape), contentAlignment = Alignment.Center) {
            Icon(icon, contentDescription = null, tint = if (kind == MovementKind.INCOME) colors.positive else colors.text2, modifier = Modifier.size(20.dp))
        }
        Column(Modifier.weight(1f).padding(horizontal = DincrSpacing.s3)) {
            Text(title, style = MaterialTheme.typography.bodyLarge, color = colors.text, maxLines = 2, overflow = TextOverflow.Ellipsis)
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (readOnly) Icon(Icons.Rounded.Lock, contentDescription = null, tint = colors.textMuted, modifier = Modifier.size(14.dp).padding(end = 2.dp))
                Text(subtitle, style = MaterialTheme.typography.bodySmall, color = colors.textMuted)
            }
        }
        MoneyText(amount, sign = if (kind == MovementKind.INCOME) MoneyFormat.Sign.INCOME else MoneyFormat.Sign.EXPENSE, currency = currency)
    }
}

/** Filled tint button: the one action that completes the task. */
@Composable
fun DincrPrimaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, enabled: Boolean = true, loading: Boolean = false) {
    Button(
        onClick = onClick, enabled = enabled && !loading,
        modifier = modifier.fillMaxWidth().heightIn(min = 52.dp),
        shape = RoundedCornerShape(DincrRadius.md),
        colors = ButtonDefaults.buttonColors(containerColor = Dincr.colors.tint, contentColor = Dincr.colors.onTint,
            disabledContainerColor = Dincr.colors.tint.copy(alpha = if (loading) 1f else 0.4f), disabledContentColor = Dincr.colors.onTint),
    ) {
        if (loading) CircularProgressIndicator(Modifier.size(20.dp), color = Dincr.colors.onTint, strokeWidth = 2.dp)
        else Text(text, style = MaterialTheme.typography.titleMedium)
    }
}

/** Loading placeholder shaped like the content; static when animations are off. */
@Composable
fun SkeletonBlock(rows: Int = 4, showsFigure: Boolean = true) {
    val animationsOn = android.provider.Settings.Global.getFloat(LocalContext.current.contentResolver, android.provider.Settings.Global.ANIMATOR_DURATION_SCALE, 1f) > 0f
    val alpha = if (animationsOn) {
        val transition = rememberInfiniteTransition(label = "skeleton")
        val value by transition.animateFloat(1f, 0.55f, infiniteRepeatable(tween(900), RepeatMode.Reverse), label = "alpha")
        value
    } else 1f
    val label = AppLanguage.current().pick("Cargando", "Loading")
    Column(Modifier.alpha(alpha).clearAndSetSemantics { contentDescription = label }, verticalArrangement = Arrangement.spacedBy(DincrSpacing.s4)) {
        if (showsFigure) DincrCard { Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) { Bar(120, 14); Bar(220, 36) } }
        DincrCard {
            Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s4)) {
                repeat(rows) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(40.dp).background(Dincr.colors.surface2, CircleShape))
                        Column(Modifier.weight(1f).padding(horizontal = DincrSpacing.s3), verticalArrangement = Arrangement.spacedBy(6.dp)) { Bar(160, 14); Bar(100, 10) }
                        Bar(70, 14)
                    }
                }
            }
        }
    }
}

@Composable
private fun Bar(width: Int, height: Int) {
    Box(Modifier.width(width.dp).height(height.dp).background(Dincr.colors.surface2, RoundedCornerShape(DincrRadius.xs)))
}

/** Empty state that teaches what will appear and offers the action that fills it. */
@Composable
fun EmptyState(icon: ImageVector, title: String, message: String, action: (@Composable () -> Unit)? = null) {
    DincrCard {
        Column(Modifier.fillMaxWidth().padding(DincrSpacing.s2), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
            Icon(icon, contentDescription = null, tint = Dincr.colors.tint, modifier = Modifier.size(32.dp))
            Text(title, style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
            Text(message, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2)
            action?.let { Spacer(Modifier.height(DincrSpacing.s1)); it() }
        }
    }
}

/** Inline error with the recovery next to it. */
@Composable
fun ErrorState(message: String, onRetry: (() -> Unit)? = null) {
    Column(Modifier.fillMaxWidth().background(Dincr.colors.negativeContainer, RoundedCornerShape(DincrRadius.md)).padding(DincrSpacing.s4)) {
        Row(verticalAlignment = Alignment.Top) {
            Icon(Icons.Rounded.Error, contentDescription = null, tint = Dincr.colors.negative)
            Text(message, style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text, modifier = Modifier.padding(start = DincrSpacing.s3))
        }
        onRetry?.let {
            TextButton(onClick = it, modifier = Modifier.heightIn(min = 48.dp)) {
                Text(AppLanguage.current().pick("Reintentar", "Try again"), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.tint)
            }
        }
    }
}

enum class BannerTone { INFO, WARNING, ERROR }

@Composable
fun StatusBanner(tone: BannerTone, title: String, message: String) {
    val c = Dincr.colors
    val (icon, color, fill) = when (tone) {
        BannerTone.INFO -> Triple(Icons.Rounded.Info, c.info, c.infoContainer)
        BannerTone.WARNING -> Triple(Icons.Rounded.Warning, c.warning, c.warningContainer)
        BannerTone.ERROR -> Triple(Icons.Rounded.Error, c.negative, c.negativeContainer)
    }
    Row(Modifier.fillMaxWidth().background(fill, RoundedCornerShape(DincrRadius.md)).padding(horizontal = DincrSpacing.s4, vertical = DincrSpacing.s3)) {
        Icon(icon, contentDescription = null, tint = color)
        Column(Modifier.padding(start = DincrSpacing.s3)) {
            Text(title, style = MaterialTheme.typography.titleMedium, color = c.text)
            Text(message, style = MaterialTheme.typography.bodyMedium, color = c.text2)
        }
    }
}

/** Single-hue bars for "where the money goes", with direct labels (no legend). */
@Composable
fun CategoryBars(items: List<Pair<String, BigDecimal>>, limit: Int = 5) {
    val shown = items.sortedByDescending { it.second }.take(limit)
    val top = shown.firstOrNull()?.second?.toDouble()?.coerceAtLeast(1.0) ?: 1.0
    Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
        shown.forEach { (label, amount) ->
            Column(Modifier.semantics(mergeDescendants = true) {}) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(label, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text)
                    MoneyText(amount, style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold))
                }
                Box(Modifier.padding(top = 6.dp).fillMaxWidth((amount.toDouble() / top).toFloat().coerceIn(0.02f, 1f)).height(6.dp).background(Dincr.colors.chartExpense, CircleShape))
            }
        }
    }
}

/** Income vs expenses per month: grouped bars in the validated series colors, legend, table. */
@Composable
fun IncomeExpenseBars(months: List<Triple<String, BigDecimal, BigDecimal>>) {
    val c = Dincr.colors
    val language = AppLanguage.current()
    val max = months.flatMap { listOf(it.second, it.third) }.maxOfOrNull { it.toDouble() }?.coerceAtLeast(1.0) ?: 1.0
    val format = Dincr.money
    val summary = months.joinToString("; ") { (m, i, e) -> "$m: ${language.pick("ingresos", "income")} ${format.spoken(i)}, ${language.pick("gastos", "expenses")} ${format.spoken(e)}" }
    Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
        Row(horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s4)) {
            Legend(c.chartIncome, language.pick("Ingresos", "Income"))
            Legend(c.chartExpense, language.pick("Gastos", "Expenses"))
        }
        Row(
            Modifier.fillMaxWidth().clearAndSetSemantics { contentDescription = summary },
            horizontalArrangement = Arrangement.SpaceEvenly, verticalAlignment = Alignment.Bottom,
        ) {
            months.forEach { (month, income, expenses) ->
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Row(Modifier.height(136.dp), verticalAlignment = Alignment.Bottom, horizontalArrangement = Arrangement.spacedBy(2.dp)) {
                        Box(Modifier.widthIn(min = 12.dp).width(14.dp).fillMaxHeightFraction(income.toDouble() / max).background(c.chartIncome, RoundedCornerShape(topStart = 4.dp, topEnd = 4.dp)))
                        Box(Modifier.width(14.dp).fillMaxHeightFraction(expenses.toDouble() / max).background(c.chartExpense, RoundedCornerShape(topStart = 4.dp, topEnd = 4.dp)))
                    }
                    Text(month, style = MaterialTheme.typography.labelSmall, color = c.textMuted, modifier = Modifier.padding(top = 4.dp))
                }
            }
        }
    }
}

private fun Modifier.fillMaxHeightFraction(fraction: Double) = fillMaxHeight(fraction.toFloat().coerceIn(0.01f, 1f))

@Composable
private fun Legend(color: androidx.compose.ui.graphics.Color, label: String) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(10.dp).background(color, CircleShape))
        Text(label, style = MaterialTheme.typography.labelMedium, color = Dincr.colors.text2, modifier = Modifier.padding(start = 6.dp))
    }
}
