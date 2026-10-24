// GENERATED from jarvis-personal/native/design-tokens/appearance.json (DINCR 2.0.0) by generate.mjs.
// Do not edit. Change appearance.json and run the generator.
import SwiftUI

public struct AppearanceNeutrals: Sendable {
    public let bg, surface, surface2, line, lineStrong, fieldBorder, text, text2, textMuted: Color
    public let positive, glow: Color?
}

public struct AppearanceAccent: Sendable {
    public let tint, tintPressed, tintContainer, onTint, onTintContainer, focusRing: Color
}

public struct AppearanceShape: Sendable {
    public let card, control: CGFloat
}

public struct AppearanceDensity: Sendable {
    public let gap, cardPadding, rowMin: CGFloat
}

public enum DincrAppearanceTokens {
    public static let palettes: [String: AppearanceNeutrals] = [
        "clasico": AppearanceNeutrals(
            bg: Color(light: 0xF5F7FA, dark: 0x0A1220),
            surface: Color(light: 0xFFFFFF, dark: 0x111B2C),
            surface2: Color(light: 0xEDF1F6, dark: 0x182438),
            line: Color(light: 0xDCE3EC, dark: 0x24324A),
            lineStrong: Color(light: 0xC3CEDC, dark: 0x34445F),
            fieldBorder: Color(light: 0x7A889E, dark: 0x65758F),
            text: Color(light: 0x0B1526, dark: 0xEEF3F9),
            text2: Color(light: 0x46546A, dark: 0xB3C0D2),
            textMuted: Color(light: 0x5B6980, dark: 0x93A2B8),
            positive: nil,
            glow: nil
        ),
        "oceano": AppearanceNeutrals(
            bg: Color(light: 0xF0F6FA, dark: 0x021221),
            surface: Color(light: 0xFFFFFF, dark: 0x091726),
            surface2: Color(light: 0xEAF2F8, dark: 0x0D2135),
            line: Color(light: 0xD3E2EE, dark: 0x123858),
            lineStrong: Color(light: 0xB6CCDD, dark: 0x1D4B70),
            fieldBorder: Color(light: 0x6A8197, dark: 0x5F84A3),
            text: Color(light: 0x0B1526, dark: 0xF2FAFF),
            text2: Color(light: 0x3F5368, dark: 0x87A6BF),
            textMuted: Color(light: 0x52677D, dark: 0x7A9CB5),
            positive: Color(light: 0x08734F, dark: 0x1FEBAB),
            glow: Color(light: 0xF6FAFD, dark: 0x041C30)
        ),
        "arena": AppearanceNeutrals(
            bg: Color(light: 0xF6F3EE, dark: 0x12100D),
            surface: Color(light: 0xFFFFFF, dark: 0x1C1915),
            surface2: Color(light: 0xEEE9E1, dark: 0x27231E),
            line: Color(light: 0xE2DBD0, dark: 0x343029),
            lineStrong: Color(light: 0xCBC1B2, dark: 0x48423A),
            fieldBorder: Color(light: 0x7F7567, dark: 0x81786B),
            text: Color(light: 0x1C1813, dark: 0xF4EFE8),
            text2: Color(light: 0x4D453A, dark: 0xC9BFB2),
            textMuted: Color(light: 0x62594D, dark: 0xA69C8F),
            positive: nil,
            glow: nil
        ),
        "grafito": AppearanceNeutrals(
            bg: Color(light: 0xF4F4F5, dark: 0x000000),
            surface: Color(light: 0xFFFFFF, dark: 0x111113),
            surface2: Color(light: 0xEBEBED, dark: 0x1C1C20),
            line: Color(light: 0xDEDEE1, dark: 0x28282D),
            lineStrong: Color(light: 0xC4C4C9, dark: 0x3A3A41),
            fieldBorder: Color(light: 0x76767F, dark: 0x74747E),
            text: Color(light: 0x111113, dark: 0xF2F2F4),
            text2: Color(light: 0x45454C, dark: 0xBDBDC4),
            textMuted: Color(light: 0x5D5D66, dark: 0x9A9AA3),
            positive: nil,
            glow: nil
        ),
    ]

    public static let accents: [String: AppearanceAccent] = [
        "teal": AppearanceAccent(
            tint: Color(light: 0x0B6E68, dark: 0x3CCFBF),
            tintPressed: Color(light: 0x085B56, dark: 0x2DB5A6),
            tintContainer: Color(light: 0xD5F0EC, dark: 0x0E3A38),
            onTint: Color(light: 0xFFFFFF, dark: 0x04201D),
            onTintContainer: Color(light: 0x053B37, dark: 0xBFF2EB),
            focusRing: Color(light: 0x0B6E68, dark: 0x3CCFBF)
        ),
        "cian": AppearanceAccent(
            tint: Color(light: 0x0068A3, dark: 0x1FB8FF),
            tintPressed: Color(light: 0x00598C, dark: 0x1AD9FF),
            tintContainer: Color(light: 0xDDF0FB, dark: 0x0D344D),
            onTint: Color(light: 0xFFFFFF, dark: 0x021221),
            onTintContainer: Color(light: 0x00405F, dark: 0xBDEBFF),
            focusRing: Color(light: 0x0068A3, dark: 0x1FB8FF)
        ),
        "ciruela": AppearanceAccent(
            tint: Color(light: 0x7A3E9D, dark: 0xD3A6F0),
            tintPressed: Color(light: 0x64317F, dark: 0xC38CE8),
            tintContainer: Color(light: 0xF1E4F8, dark: 0x33193F),
            onTint: Color(light: 0xFFFFFF, dark: 0x22102C),
            onTintContainer: Color(light: 0x3A1650, dark: 0xF2DDFB),
            focusRing: Color(light: 0x7A3E9D, dark: 0xD3A6F0)
        ),
        "tinta": AppearanceAccent(
            tint: Color(light: 0x1A2233, dark: 0xE8ECF3),
            tintPressed: Color(light: 0x0E1420, dark: 0xCDD3DD),
            tintContainer: Color(light: 0xE3E7EE, dark: 0x283246),
            onTint: Color(light: 0xFFFFFF, dark: 0x0B1020),
            onTintContainer: Color(light: 0x1A2233, dark: 0xE8ECF3),
            focusRing: Color(light: 0x1A2233, dark: 0xE8ECF3)
        ),
    ]

    public static let shapes: [String: AppearanceShape] = [
        "outlined": AppearanceShape(card: 22, control: 16),
        "tonal": AppearanceShape(card: 20, control: 14),
    ]

    public static let density: [String: AppearanceDensity] = [
        "comfortable": AppearanceDensity(gap: 16, cardPadding: 16, rowMin: 56),
        "compact": AppearanceDensity(gap: 12, cardPadding: 12, rowMin: 48),
    ]
}
