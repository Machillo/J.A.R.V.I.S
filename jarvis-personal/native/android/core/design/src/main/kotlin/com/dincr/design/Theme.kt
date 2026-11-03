package com.dincr.design

import androidx.compose.foundation.background
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.Dp
import com.dincr.data.AppearancePrefs
import androidx.compose.ui.unit.sp
import com.dincr.data.MoneyFormat
import com.dincr.design.generated.DincrAppearanceTokens
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
    /** The solid top of Hoy and the welcome story, with its secondary control and text. */
    val scene: Color = Color(0xFF2A2E6E), val sceneControl: Color = Color(0xFF3D4290), val onScene2: Color = Color(0xFFD9DBF5),
)

/** One of the color styles a person may pick (`color-styles.json`). [colors] null is the default scene. */
data class DincrColorStyle(val id: String, val nameEs: String, val nameEn: String, val swatches: List<Color>, val colors: DincrStyleColors?)

data class DincrStyleColors(
    val bg: DincrColorPair, val surface: DincrColorPair, val surface2: DincrColorPair, val line: DincrColorPair, val lineStrong: DincrColorPair, val fieldBorder: DincrColorPair,
    val text: DincrColorPair, val text2: DincrColorPair, val textMuted: DincrColorPair,
    val tint: DincrColorPair, val tintPressed: DincrColorPair, val tintContainer: DincrColorPair, val onTint: DincrColorPair, val onTintContainer: DincrColorPair,
    val hero: Color, val heroControl: Color, val onHero2: Color,
)

/** The palette with a color style on top: neutrals, accent and hero; status and chart colors keep their meaning. */
internal fun DincrPalette.styled(style: DincrStyleColors?, dark: Boolean): DincrPalette {
    if (style == null) return this
    fun DincrColorPair.pick() = if (dark) this.dark else light
    return copy(
        bg = style.bg.pick(), surface = style.surface.pick(), surface2 = style.surface2.pick(), line = style.line.pick(), lineStrong = style.lineStrong.pick(), fieldBorder = style.fieldBorder.pick(),
        text = style.text.pick(), text2 = style.text2.pick(), textMuted = style.textMuted.pick(),
        tint = style.tint.pick(), tintPressed = style.tintPressed.pick(), tintContainer = style.tintContainer.pick(), onTint = style.onTint.pick(), onTintContainer = style.onTintContainer.pick(),
        scene = style.hero, sceneControl = style.heroControl, onScene2 = style.onHero2,
    )
}

/**
 * The palette of an appearance: its neutrals and accent (appearance.json) over DESIGN.md's status
 * and chart colors. The classic appearance is DESIGN.md exactly (enforced by the token generator).
 */
internal fun palette(dark: Boolean, appearance: AppearancePrefs = AppearancePrefs.CLASSIC): DincrPalette {
    fun DincrColorPair.pick() = if (dark) this.dark else light
    val prefs = appearance.sanitized()
    val n = DincrAppearanceTokens.palettes.getValue(prefs.palette).pick(dark)
    val a = DincrAppearanceTokens.accents.getValue(prefs.accent).pick(dark)
    return with(DincrColors) {
        DincrPalette(
            n.bg, n.surface, n.surface2, n.line, n.lineStrong, n.fieldBorder,
            n.text, n.text2, n.textMuted,
            a.tint, a.tintPressed, a.tintContainer, a.onTint, a.onTintContainer,
            n.positive ?: positive.pick(), positiveContainer.pick(), negative.pick(), negativeContainer.pick(),
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
 * Shapes, spacing and surfaces of an appearance (appearance.json → shapes, density). The classic
 * values are DESIGN.md's: cards `rounded.lg`, controls `rounded.md`, gaps and padding `spacing.4`,
 * rows 56, tonal cards with a hairline edge (DincrCard), a flat background.
 */
@Immutable
data class DincrLook(
    val cardRadius: Dp, val controlRadius: Dp, val cardPadding: Dp, val gap: Dp, val rowMin: Dp,
    /** A hairline (`line`) around cards: the Owner identity's surfaces. */
    val outlined: Boolean,
    /** The scene's quiet radial at the top of the screen (Océano), or null for a flat background. */
    val glow: Color?,
    /** Serif screen and section titles; amounts and body text stay in the system face. */
    val editorial: Boolean,
) {
    companion object {
        fun of(appearance: AppearancePrefs, dark: Boolean): DincrLook {
            val prefs = appearance.sanitized()
            val shape = DincrAppearanceTokens.shapes.getValue(prefs.surfaces)
            val density = DincrAppearanceTokens.density.getValue(prefs.density)
            return DincrLook(
                cardRadius = shape.card, controlRadius = shape.control, cardPadding = density.cardPadding, gap = density.gap, rowMin = density.rowMin,
                outlined = prefs.surfaces == "outlined",
                glow = DincrAppearanceTokens.palettes.getValue(prefs.palette).pick(dark).glow,
                editorial = prefs.typeface == "editorial",
            )
        }

        val CLASSIC = of(AppearancePrefs.CLASSIC, dark = false)
    }
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
val LocalDincrLook = staticCompositionLocalOf { DincrLook.CLASSIC }
private val LocalAppearanceTextScale = staticCompositionLocalOf { 1f }

/**
 * [content] at the system font scale only, without the personal text size: for fixed, one-line
 * platform chrome (the bottom bar's five labels), which would be cut instead of growing.
 */
@Composable
fun SystemTextScale(content: @Composable () -> Unit) {
    val scale = LocalAppearanceTextScale.current
    if (scale == 1f) return content()
    val density = LocalDensity.current
    CompositionLocalProvider(LocalDensity provides Density(density.density, density.fontScale / scale), LocalAppearanceTextScale provides 1f, content = content)
}

object Dincr {
    val colors: DincrPalette @Composable @ReadOnlyComposable get() = LocalDincrPalette.current
    val money: MoneyFormat @Composable @ReadOnlyComposable get() = LocalMoneyFormat.current
    val look: DincrLook @Composable @ReadOnlyComposable get() = LocalDincrLook.current
}

/**
 * Typography roles (DESIGN.md → Typography) on the Material scale, in sp so font scaling applies.
 * DINCR 3.0: titles are set semibold and slightly tight, money figures bold, labels medium.
 */
private fun typography(editorial: Boolean = false): Typography {
    val t = Typography()
    val tight = (-0.4).sp
    val base = t.copy(
        displaySmall = t.displaySmall.copy(fontWeight = FontWeight.Bold, letterSpacing = (-0.6).sp),
        headlineMedium = t.headlineMedium.copy(fontWeight = FontWeight.SemiBold, letterSpacing = tight),
        headlineSmall = t.headlineSmall.copy(fontWeight = FontWeight.Bold, letterSpacing = tight),
        titleLarge = t.titleLarge.copy(fontWeight = FontWeight.SemiBold, letterSpacing = (-0.2).sp),
        titleMedium = t.titleMedium.copy(fontWeight = FontWeight.SemiBold),
        labelLarge = t.labelLarge.copy(fontWeight = FontWeight.SemiBold, letterSpacing = 0.2.sp),
    )
    if (!editorial) return base
    // Editorial: screen, sheet and section titles in the platform serif. Amounts (display), card
    // titles, buttons, body and labels keep the system face and tabular digits.
    val serif = FontFamily.Serif
    return base.copy(
        headlineLarge = base.headlineLarge.copy(fontFamily = serif),
        headlineMedium = base.headlineMedium.copy(fontFamily = serif, fontWeight = FontWeight.SemiBold),
        headlineSmall = base.headlineSmall.copy(fontFamily = serif),
        titleLarge = base.titleLarge.copy(fontFamily = serif, fontWeight = FontWeight.SemiBold),
    )
}

/**
 * DINCR's theme. [appearance] is the account's personal appearance (APP-1, the Owner only in
 * phase 1); every other account gets [AppearancePrefs.CLASSIC], which is today's DINCR exactly.
 */
@Composable
fun DincrTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    moneyFormat: MoneyFormat = MoneyFormat(),
    appearance: AppearancePrefs = AppearancePrefs.OWNER_DEFAULT,
    colorStyle: String = com.dincr.design.generated.DincrColorStyles.DEFAULT_ID,
    content: @Composable () -> Unit,
) {
    val p = palette(darkTheme, appearance).styled(com.dincr.design.generated.DincrColorStyles.all.firstOrNull { it.id == colorStyle }?.colors, darkTheme)
    val look = DincrLook.of(appearance, darkTheme)
    val scale = appearance.textScale
    val density = LocalDensity.current
    CompositionLocalProvider(
        LocalDincrPalette provides p, LocalMoneyFormat provides moneyFormat, LocalDincrLook provides look, LocalAppearanceTextScale provides scale,
        // The chosen text size multiplies the system font scale, never replaces it.
        LocalDensity provides if (scale == 1f) density else Density(density.density, density.fontScale * scale),
    ) {
        MaterialTheme(colorScheme = scheme(p, darkTheme), typography = typography(look.editorial), content = content)
    }
}

/** The screen background: the palette's `bg`, with the scene's quiet radial from the top when it has one. */
@Composable
fun Modifier.dincrScreenBackground(): Modifier {
    val bg = Dincr.colors.bg
    val glow = Dincr.look.glow ?: return background(bg)
    return background(bg).drawBehind {
        drawRect(Brush.radialGradient(listOf(glow, bg), center = Offset(size.width / 2, 0f), radius = size.maxDimension.coerceAtLeast(1f)))
    }
}
