// GENERATED from jarvis-personal/native/design-tokens/appearance.json (DINCR 3.0.0) by generate.mjs.
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
            bg: Color(light: 0xF2F5F9, dark: 0x070E1A),
            surface: Color(light: 0xFFFFFF, dark: 0x0F1A2B),
            surface2: Color(light: 0xE8EDF4, dark: 0x172539),
            line: Color(light: 0xDCE3EC, dark: 0x22324A),
            lineStrong: Color(light: 0xC2CCDA, dark: 0x33445F),
            fieldBorder: Color(light: 0x6F7E96, dark: 0x6A7A94),
            text: Color(light: 0x0A1628, dark: 0xEDF2F9),
            text2: Color(light: 0x3F4D66, dark: 0xB3C0D2),
            textMuted: Color(light: 0x56647C, dark: 0x94A3B9),
            positive: nil,
            glow: nil
        ),
        "oceano": AppearanceNeutrals(
            bg: Color(light: 0xF2F2F7, dark: 0x0A0B1E),
            surface: Color(light: 0xFFFFFF, dark: 0x1C1E3A),
            surface2: Color(light: 0xEFEFF4, dark: 0x2A2D52),
            line: Color(light: 0xD1D1D6, dark: 0x33365C),
            lineStrong: Color(light: 0xC7C7CC, dark: 0x454873),
            fieldBorder: Color(light: 0x86868B, dark: 0x8A8DB0),
            text: Color(light: 0x1C1C1E, dark: 0xF5F5F7),
            text2: Color(light: 0x4F4F55, dark: 0xB4B6CC),
            textMuted: Color(light: 0x636366, dark: 0xA3A5BD),
            positive: Color(light: 0x08734F, dark: 0x30D158),
            glow: Color(light: 0xF2F2F7, dark: 0x0A0B1E)
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
            tint: Color(light: 0x0A6B5C, dark: 0x45D3BC),
            tintPressed: Color(light: 0x075447, dark: 0x33B9A4),
            tintContainer: Color(light: 0xD2F0E7, dark: 0x0C3A34),
            onTint: Color(light: 0xFFFFFF, dark: 0x03201B),
            onTintContainer: Color(light: 0x03372E, dark: 0xC0F2E8),
            focusRing: Color(light: 0x0A6B5C, dark: 0x45D3BC)
        ),
        "cian": AppearanceAccent(
            tint: Color(light: 0x4A4FD9, dark: 0x8F95FF),
            tintPressed: Color(light: 0x3B3FB8, dark: 0xB0B4FF),
            tintContainer: Color(light: 0xE8E9FC, dark: 0x24275C),
            onTint: Color(light: 0xFFFFFF, dark: 0x0B0C2A),
            onTintContainer: Color(light: 0x2A2D8F, dark: 0xD6D8FF),
            focusRing: Color(light: 0x4A4FD9, dark: 0x8F95FF)
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
        "outlined": AppearanceShape(card: 16, control: 12),
        "tonal": AppearanceShape(card: 20, control: 14),
    ]

    public static let density: [String: AppearanceDensity] = [
        "comfortable": AppearanceDensity(gap: 16, cardPadding: 16, rowMin: 56),
        "compact": AppearanceDensity(gap: 12, cardPadding: 12, rowMin: 48),
    ]
}
