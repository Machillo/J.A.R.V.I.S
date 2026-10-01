import SwiftUI

/// DINCR Owner identity (the single Owner account and its personal layer, JARVIS).
///
/// The Owner is not a plan: DESIGN.md's "plans don't repaint the app" still holds for Free, Basic and
/// VIP. The Owner's screens keep DINCR's structure, type and components and change only the scene:
/// a deep petrol background, blue-tinted surfaces with a hairline border, and a cyan accent (DESIGN.md
/// → Owner identity). Light and dark both exist, because DINCR follows the system appearance; the
/// light values are derived from the dark design and keep WCAG AA (≥ 4.5:1) for text on every
/// Owner surface.
///
/// Screens never read these directly to decide *whether* they are the Owner's: the root sets
/// `dincrOwnerAppearance` from the server role, and the shared modifiers and components read it.
public enum OwnerColor {
    /// Background gradient stops: petrol at the top centre, almost black at the edges (dark).
    public static let backgroundCenter = Color(light: 0xF6FAFD, dark: 0x041C30)
    public static let backgroundMiddle = Color(light: 0xF0F6FA, dark: 0x021221)
    public static let backgroundEdge = Color(light: 0xEAF1F7, dark: 0x000306)
    /// Cards and grouped rows (the design's rgba(9,23,38,0.96), opaque for legibility).
    public static let surface = Color(light: 0xFFFFFF, dark: 0x091726)
    /// Nested regions inside a surface: icon wells, fields.
    public static let surface2 = Color(light: 0xEAF2F8, dark: 0x0D2135)
    /// Hairline around Owner surfaces (decorative only; never the only boundary of a control).
    public static let border = Color(light: 0xD3E2EE, dark: 0x123858)
    /// The Owner accent: actions, links, selection, JARVIS.
    public static let accent = Color(light: 0x0068A3, dark: 0x1FB8FF)
    /// Pressed / active state of the accent.
    public static let accentActive = Color(light: 0x00598C, dark: 0x1AD9FF)
    public static let onAccent = Color(light: 0xFFFFFF, dark: 0x021221)
    /// Tonal container of the accent: secondary buttons, quick actions, icon wells.
    public static let accentContainer = Color(light: 0xDDF0FB, dark: 0x0D344D)
    public static let onAccentContainer = Color(light: 0x00405F, dark: 0xBDEBFF)
    public static let positive = Color(light: 0x08734F, dark: 0x1FEBAB)
    public static let text = Color(light: 0x0B1526, dark: 0xF2FAFF)
    public static let text2 = Color(light: 0x3F5368, dark: 0x87A6BF)
    public static let textMuted = Color(light: 0x52677D, dark: 0x7A9CB5)
    /// Chart series beyond income/expense. Color always repeats a meaning that is also in text.
    public static let chartCyan = Color(light: 0x0068A3, dark: 0x1FB8FF)
    public static let chartGreen = Color(light: 0x08734F, dark: 0x1FEBAB)
    public static let chartOrange = Color(light: 0xB4501F, dark: 0xFF855C)
    public static let chartPurple = Color(light: 0x7A45C2, dark: 0xB078F2)
}

/// Owner shapes: one card radius, one control radius (the design's 22 / 18).
public enum OwnerRadius {
    public static let card: CGFloat = 22
    public static let control: CGFloat = 18
}

private struct OwnerAppearanceKey: EnvironmentKey {
    static let defaultValue = false
}

public extension EnvironmentValues {
    /// True only below the root of a signed-in Owner (server role in `/auth/me`). Shared modifiers
    /// and components switch to the Owner scene; every other account keeps DINCR's default look.
    var dincrOwnerAppearance: Bool {
        get { self[OwnerAppearanceKey.self] }
        set { self[OwnerAppearanceKey.self] = newValue }
    }
}

/// The Owner's screen background: a quiet radial from petrol to near black (dark) or from white to a
/// pale blue (light). With Increase Contrast it is a single flat color.
public struct OwnerBackground: View {
    @Environment(\.colorSchemeContrast) private var contrast

    public init() {}

    public var body: some View {
        if contrast == .increased {
            OwnerColor.backgroundMiddle
        } else {
            RadialGradient(
                colors: [OwnerColor.backgroundCenter, OwnerColor.backgroundMiddle, OwnerColor.backgroundEdge],
                center: UnitPoint(x: 0.5, y: 0), startRadius: 0, endRadius: 900
            )
        }
    }
}

/// JARVIS's mark: a calm cyan orb (two concentric rings and a soft core). Static, so it never moves
/// under Reduce Motion and never distracts; decorative unless the caller gives it a label.
public struct JarvisMark: View {
    let size: CGFloat

    public init(size: CGFloat = 44) {
        self.size = size
    }

    public var body: some View {
        ZStack {
            Circle()
                .fill(RadialGradient(colors: [OwnerColor.accent.opacity(0.35), OwnerColor.accent.opacity(0)],
                                     center: .center, startRadius: 0, endRadius: size * 0.5))
            Circle()
                .strokeBorder(OwnerColor.accent.opacity(0.35), lineWidth: max(1, size * 0.03))
                .padding(size * 0.08)
            Circle()
                .strokeBorder(OwnerColor.accentActive.opacity(0.8), lineWidth: max(1, size * 0.04))
                .padding(size * 0.24)
            Circle()
                .fill(OwnerColor.accentActive)
                .frame(width: size * 0.18, height: size * 0.18)
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }
}

/// A quiet group container of the Owner: one surface for a set of related rows (never one card per
/// record). Rows inside are separated by `OwnerDivider`.
public struct OwnerGroup<Content: View>: View {
    let content: Content

    public init(@ViewBuilder content: () -> Content) {
        self.content = content()
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 0) { content }
            .padding(.horizontal, DincrSpacing.s4)
            .padding(.vertical, DincrSpacing.s1)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(OwnerColor.surface, in: RoundedRectangle(cornerRadius: OwnerRadius.card, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: OwnerRadius.card, style: .continuous).strokeBorder(OwnerColor.border, lineWidth: 1))
    }
}

/// The separator between rows of an `OwnerGroup`.
public struct OwnerDivider: View {
    public init() {}
    public var body: some View {
        Rectangle().fill(OwnerColor.border).frame(height: 1).accessibilityHidden(true)
    }
}

/// One row of an Owner group: a symbol in a tonal well, a title, an optional detail, an optional
/// trailing value and a chevron when it navigates. At least 44 pt tall; text wraps at large sizes.
public struct OwnerRow<Trailing: View>: View {
    let symbol: String
    let title: String
    let detail: String?
    let tone: Tone
    let showsChevron: Bool
    let trailing: Trailing

    public enum Tone: Sendable { case accent, warning, negative, neutral }

    public init(symbol: String, title: String, detail: String? = nil, tone: Tone = .accent, showsChevron: Bool = true,
                @ViewBuilder trailing: () -> Trailing) {
        self.symbol = symbol; self.title = title; self.detail = detail; self.tone = tone
        self.showsChevron = showsChevron; self.trailing = trailing()
    }

    public var body: some View {
        HStack(spacing: DincrSpacing.s3) {
            Image(systemName: symbol)
                .font(.body.weight(.medium))
                .foregroundStyle(iconColor)
                .frame(width: 36, height: 36)
                .background(wellColor, in: RoundedRectangle(cornerRadius: DincrRadius.sm, style: .continuous))
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(DincrFont.body.weight(.semibold)).foregroundStyle(OwnerColor.text)
                if let detail, !detail.isEmpty {
                    Text(detail).font(DincrFont.caption).foregroundStyle(OwnerColor.text2)
                }
            }
            Spacer(minLength: DincrSpacing.s2)
            trailing
            if showsChevron {
                Image(systemName: "chevron.right").font(.footnote.weight(.semibold)).foregroundStyle(OwnerColor.textMuted)
                    .accessibilityHidden(true)
            }
        }
        .padding(.vertical, DincrSpacing.s3)
        .frame(minHeight: 44)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    private var iconColor: Color {
        switch tone {
        case .accent: OwnerColor.accent
        case .warning: DincrColor.warning
        case .negative: DincrColor.negative
        case .neutral: OwnerColor.text2
        }
    }

    private var wellColor: Color {
        switch tone {
        case .accent: OwnerColor.accentContainer
        case .warning: DincrColor.warningContainer
        case .negative: DincrColor.negativeContainer
        case .neutral: OwnerColor.surface2
        }
    }
}

public extension OwnerRow where Trailing == EmptyView {
    init(symbol: String, title: String, detail: String? = nil, tone: Tone = .accent, showsChevron: Bool = true) {
        self.init(symbol: symbol, title: title, detail: detail, tone: tone, showsChevron: showsChevron) { EmptyView() }
    }
}

/// An Owner section heading: a title, and an optional trailing link-sized accessory.
public struct OwnerSectionHeader<Accessory: View>: View {
    let title: String
    let accessory: Accessory

    public init(_ title: String, @ViewBuilder accessory: () -> Accessory) {
        self.title = title; self.accessory = accessory()
    }

    public var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title).font(DincrFont.title2).foregroundStyle(OwnerColor.text).accessibilityAddTraits(.isHeader)
            Spacer(minLength: DincrSpacing.s2)
            accessory.font(DincrFont.bodySmall.weight(.semibold)).foregroundStyle(OwnerColor.accent)
        }
        // With the parent's 16 pt spacing: more room above a heading than below it (DESIGN.md → Layout).
        .padding(.top, DincrSpacing.s2)
    }
}

public extension OwnerSectionHeader where Accessory == EmptyView {
    init(_ title: String) {
        self.init(title) { EmptyView() }
    }
}

/// A compact tonal action (JARVIS quick actions): symbol and label, at least 44 pt, wraps at large
/// text sizes instead of truncating.
public struct OwnerQuickActionStyle: ButtonStyle {
    public init() {}

    public func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(DincrFont.bodySmall.weight(.semibold))
            .foregroundStyle(OwnerColor.onAccentContainer)
            .multilineTextAlignment(.leading)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .padding(.horizontal, DincrSpacing.s3)
            .padding(.vertical, DincrSpacing.s2)
            .background(OwnerColor.accentContainer, in: RoundedRectangle(cornerRadius: OwnerRadius.control, style: .continuous))
            .opacity(configuration.isPressed ? 0.8 : 1)
            .contentShape(Rectangle())
    }
}

public extension ButtonStyle where Self == OwnerQuickActionStyle {
    static var ownerQuickAction: OwnerQuickActionStyle { OwnerQuickActionStyle() }
}
