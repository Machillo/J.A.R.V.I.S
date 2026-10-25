// GENERATED from jarvis-personal/native/design-tokens/appearance.json (DINCR 2.0.0) by generate.mjs.
// Do not edit. Change appearance.json and run the generator.
package com.dincr.design.generated

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

data class AppearancePair<T>(val light: T, val dark: T) {
    fun pick(dark: Boolean): T = if (dark) this.dark else light
}

data class AppearanceNeutrals(
    val bg: Color, val surface: Color, val surface2: Color, val line: Color, val lineStrong: Color, val fieldBorder: Color,
    val text: Color, val text2: Color, val textMuted: Color, val positive: Color?, val glow: Color?,
)

data class AppearanceAccent(val tint: Color, val tintPressed: Color, val tintContainer: Color, val onTint: Color, val onTintContainer: Color, val focusRing: Color)

data class AppearanceShape(val card: Dp, val control: Dp)

data class AppearanceDensity(val gap: Dp, val cardPadding: Dp, val rowMin: Dp)

object DincrAppearanceTokens {
    val palettes: Map<String, AppearancePair<AppearanceNeutrals>> = linkedMapOf(
        "clasico" to AppearancePair(
            light = AppearanceNeutrals(bg = Color(0xFFF5F7FA), surface = Color(0xFFFFFFFF), surface2 = Color(0xFFEDF1F6), line = Color(0xFFDCE3EC), lineStrong = Color(0xFFC3CEDC), fieldBorder = Color(0xFF7A889E), text = Color(0xFF0B1526), text2 = Color(0xFF46546A), textMuted = Color(0xFF5B6980), positive = null, glow = null),
            dark = AppearanceNeutrals(bg = Color(0xFF0A1220), surface = Color(0xFF111B2C), surface2 = Color(0xFF182438), line = Color(0xFF24324A), lineStrong = Color(0xFF34445F), fieldBorder = Color(0xFF65758F), text = Color(0xFFEEF3F9), text2 = Color(0xFFB3C0D2), textMuted = Color(0xFF93A2B8), positive = null, glow = null),
        ),
        "oceano" to AppearancePair(
            light = AppearanceNeutrals(bg = Color(0xFFF0F6FA), surface = Color(0xFFFFFFFF), surface2 = Color(0xFFEAF2F8), line = Color(0xFFD3E2EE), lineStrong = Color(0xFFB6CCDD), fieldBorder = Color(0xFF6A8197), text = Color(0xFF0B1526), text2 = Color(0xFF3F5368), textMuted = Color(0xFF52677D), positive = Color(0xFF08734F), glow = Color(0xFFF6FAFD)),
            dark = AppearanceNeutrals(bg = Color(0xFF021221), surface = Color(0xFF091726), surface2 = Color(0xFF0D2135), line = Color(0xFF123858), lineStrong = Color(0xFF1D4B70), fieldBorder = Color(0xFF5F84A3), text = Color(0xFFF2FAFF), text2 = Color(0xFF87A6BF), textMuted = Color(0xFF7A9CB5), positive = Color(0xFF1FEBAB), glow = Color(0xFF041C30)),
        ),
        "arena" to AppearancePair(
            light = AppearanceNeutrals(bg = Color(0xFFF6F3EE), surface = Color(0xFFFFFFFF), surface2 = Color(0xFFEEE9E1), line = Color(0xFFE2DBD0), lineStrong = Color(0xFFCBC1B2), fieldBorder = Color(0xFF7F7567), text = Color(0xFF1C1813), text2 = Color(0xFF4D453A), textMuted = Color(0xFF62594D), positive = null, glow = null),
            dark = AppearanceNeutrals(bg = Color(0xFF12100D), surface = Color(0xFF1C1915), surface2 = Color(0xFF27231E), line = Color(0xFF343029), lineStrong = Color(0xFF48423A), fieldBorder = Color(0xFF81786B), text = Color(0xFFF4EFE8), text2 = Color(0xFFC9BFB2), textMuted = Color(0xFFA69C8F), positive = null, glow = null),
        ),
        "grafito" to AppearancePair(
            light = AppearanceNeutrals(bg = Color(0xFFF4F4F5), surface = Color(0xFFFFFFFF), surface2 = Color(0xFFEBEBED), line = Color(0xFFDEDEE1), lineStrong = Color(0xFFC4C4C9), fieldBorder = Color(0xFF76767F), text = Color(0xFF111113), text2 = Color(0xFF45454C), textMuted = Color(0xFF5D5D66), positive = null, glow = null),
            dark = AppearanceNeutrals(bg = Color(0xFF000000), surface = Color(0xFF111113), surface2 = Color(0xFF1C1C20), line = Color(0xFF28282D), lineStrong = Color(0xFF3A3A41), fieldBorder = Color(0xFF74747E), text = Color(0xFFF2F2F4), text2 = Color(0xFFBDBDC4), textMuted = Color(0xFF9A9AA3), positive = null, glow = null),
        ),
    )

    val accents: Map<String, AppearancePair<AppearanceAccent>> = linkedMapOf(
        "teal" to AppearancePair(
            light = AppearanceAccent(tint = Color(0xFF0B6E68), tintPressed = Color(0xFF085B56), tintContainer = Color(0xFFD5F0EC), onTint = Color(0xFFFFFFFF), onTintContainer = Color(0xFF053B37), focusRing = Color(0xFF0B6E68)),
            dark = AppearanceAccent(tint = Color(0xFF3CCFBF), tintPressed = Color(0xFF2DB5A6), tintContainer = Color(0xFF0E3A38), onTint = Color(0xFF04201D), onTintContainer = Color(0xFFBFF2EB), focusRing = Color(0xFF3CCFBF)),
        ),
        "cian" to AppearancePair(
            light = AppearanceAccent(tint = Color(0xFF0068A3), tintPressed = Color(0xFF00598C), tintContainer = Color(0xFFDDF0FB), onTint = Color(0xFFFFFFFF), onTintContainer = Color(0xFF00405F), focusRing = Color(0xFF0068A3)),
            dark = AppearanceAccent(tint = Color(0xFF1FB8FF), tintPressed = Color(0xFF1AD9FF), tintContainer = Color(0xFF0D344D), onTint = Color(0xFF021221), onTintContainer = Color(0xFFBDEBFF), focusRing = Color(0xFF1FB8FF)),
        ),
        "ciruela" to AppearancePair(
            light = AppearanceAccent(tint = Color(0xFF7A3E9D), tintPressed = Color(0xFF64317F), tintContainer = Color(0xFFF1E4F8), onTint = Color(0xFFFFFFFF), onTintContainer = Color(0xFF3A1650), focusRing = Color(0xFF7A3E9D)),
            dark = AppearanceAccent(tint = Color(0xFFD3A6F0), tintPressed = Color(0xFFC38CE8), tintContainer = Color(0xFF33193F), onTint = Color(0xFF22102C), onTintContainer = Color(0xFFF2DDFB), focusRing = Color(0xFFD3A6F0)),
        ),
        "tinta" to AppearancePair(
            light = AppearanceAccent(tint = Color(0xFF1A2233), tintPressed = Color(0xFF0E1420), tintContainer = Color(0xFFE3E7EE), onTint = Color(0xFFFFFFFF), onTintContainer = Color(0xFF1A2233), focusRing = Color(0xFF1A2233)),
            dark = AppearanceAccent(tint = Color(0xFFE8ECF3), tintPressed = Color(0xFFCDD3DD), tintContainer = Color(0xFF283246), onTint = Color(0xFF0B1020), onTintContainer = Color(0xFFE8ECF3), focusRing = Color(0xFFE8ECF3)),
        ),
    )

    val shapes: Map<String, AppearanceShape> = linkedMapOf(
        "outlined" to AppearanceShape(card = 22.dp, control = 16.dp),
        "tonal" to AppearanceShape(card = 20.dp, control = 14.dp),
    )

    val density: Map<String, AppearanceDensity> = linkedMapOf(
        "comfortable" to AppearanceDensity(gap = 16.dp, cardPadding = 16.dp, rowMin = 56.dp),
        "compact" to AppearanceDensity(gap = 12.dp, cardPadding = 12.dp, rowMin = 48.dp),
    )
}
