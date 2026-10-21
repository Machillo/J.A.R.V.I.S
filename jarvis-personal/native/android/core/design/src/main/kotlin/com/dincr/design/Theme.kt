package com.dincr.design

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.ReadOnlyComposable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp
import com.dincr.data.MoneyFormat
import com.dincr.design.generated.DincrColorPair
import com.dincr.design.generated.DincrColors

/** Resolved DINCR semantic colors for the current scheme (DESIGN.md → Colors). */
@Immutable
data class DincrPalette(
    val bg: Color, val surface: Color, val surface2: Color, val line: Color, val lineStrong: Color, val fieldBorder: Color,
    val text: Color, val text2: Color, val textMuted: Color,
    val tint: Color, val tintPressed: Color, val tintContainer: Color, val onTint: Color, val onTintContainer: Color,
    val positive: Color, val positiveContainer: Color, val negative: Color, val negativeContainer: Color,
    val warning: Color, val warningContainer: Color, val info: Color, val infoContainer: Color,
    val vip: Color, val vipContainer: Color, val chartIncome: Color, val chartExpense: Color,
    val hero: Color, val hero2: Color, val onHero: Color, val onHero2: Color, val heroAccent: Color,
)

private fun palette(dark: Boolean): DincrPalette {
    fun DincrColorPair.pick() = if (dark) this.dark else light
    return with(DincrColors) {
        DincrPalette(
            bg.pick(), surface.pick(), surface2.pick(), line.pick(), lineStrong.pick(), fieldBorder.pick(),
            text.pick(), text2.pick(), textMuted.pick(),
            tint.pick(), tintPressed.pick(), tintContainer.pick(), onTint.pick(), onTintContainer.pick(),
            positive.pick(), positiveContainer.pick(), negative.pick(), negativeContainer.pick(),
            warning.pick(), warningContainer.pick(), info.pick(), infoContainer.pick(),
            vip.pick(), vipContainer.pick(), chartIncome.pick(), chartExpense.pick(),
            hero.pick(), hero2.pick(), onHero.pick(), onHero2.pick(), heroAccent.pick(),
        )
    }
}

/** Material color roles mapped from DINCR tokens. Dynamic Color stays off (DESIGN_REVIEWS R1 #15). */
private fun scheme(p: DincrPalette, dark: Boolean): ColorScheme {
    val base = if (dark) darkColorScheme() else lightColorScheme()
    return base.copy(
        primary = p.tint, onPrimary = p.onTint, primaryContainer = p.tintContainer, onPrimaryContainer = p.onTintContainer,
        secondary = p.tint, onSecondary = p.onTint, secondaryContainer = p.tintContainer, onSecondaryContainer = p.onTintContainer,
        background = p.bg, onBackground = p.text, surface = p.bg, onSurface = p.text,
        surfaceVariant = p.surface2, onSurfaceVariant = p.text2,
        surfaceContainerLowest = p.surface, surfaceContainerLow = p.surface, surfaceContainer = p.surface,
        surfaceContainerHigh = p.surface2, surfaceContainerHighest = p.surface2, surfaceBright = p.surface,
        outline = p.fieldBorder, outlineVariant = p.line,
        error = p.negative, onError = p.onTint, errorContainer = p.negativeContainer, onErrorContainer = p.text,
    )
}

/**
 * Colors inside a hero card (DESIGN.md → Hero card): the dark scheme's roles on the hero surface,
 * so every nested component (figures, captions, bars, status text) stays readable on ink in
 * both schemes. The pairs are in the design-token contrast gate.
 */
fun heroPalette(p: DincrPalette): DincrPalette = palette(true).copy(
    bg = p.hero, surface = p.hero, surface2 = p.onHero.copy(alpha = 0.16f), line = p.hero2, lineStrong = p.hero2,
    text = p.onHero, text2 = p.onHero2, textMuted = p.onHero2,
    hero = p.hero, hero2 = p.hero2, onHero = p.onHero, onHero2 = p.onHero2, heroAccent = p.heroAccent,
)

val LocalDincrPalette = staticCompositionLocalOf { palette(false) }
val LocalMoneyFormat = staticCompositionLocalOf { MoneyFormat() }

object Dincr {
    val colors: DincrPalette @Composable @ReadOnlyComposable get() = LocalDincrPalette.current
    val money: MoneyFormat @Composable @ReadOnlyComposable get() = LocalMoneyFormat.current
}

/**
 * Typography roles (DESIGN.md → Typography) on the Material scale, in sp so font scaling applies.
 * DINCR 3.0: titles are set semibold and slightly tight, money figures bold, labels medium.
 */
private fun typography(): Typography {
    val t = Typography()
    val tight = (-0.4).sp
    return t.copy(
        displaySmall = t.displaySmall.copy(fontWeight = FontWeight.Bold, letterSpacing = (-0.6).sp),
        headlineMedium = t.headlineMedium.copy(fontWeight = FontWeight.SemiBold, letterSpacing = tight),
        headlineSmall = t.headlineSmall.copy(fontWeight = FontWeight.Bold, letterSpacing = tight),
        titleLarge = t.titleLarge.copy(fontWeight = FontWeight.SemiBold, letterSpacing = (-0.2).sp),
        titleMedium = t.titleMedium.copy(fontWeight = FontWeight.SemiBold),
        labelLarge = t.labelLarge.copy(fontWeight = FontWeight.SemiBold, letterSpacing = 0.2.sp),
    )
}

@Composable
fun DincrTheme(darkTheme: Boolean = isSystemInDarkTheme(), moneyFormat: MoneyFormat = MoneyFormat(), content: @Composable () -> Unit) {
    val p = palette(darkTheme)
    CompositionLocalProvider(LocalDincrPalette provides p, LocalMoneyFormat provides moneyFormat) {
        MaterialTheme(colorScheme = scheme(p, darkTheme), typography = typography(), content = content)
    }
}
