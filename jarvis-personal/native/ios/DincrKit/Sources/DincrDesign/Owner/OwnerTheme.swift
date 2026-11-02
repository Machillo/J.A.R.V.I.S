import SwiftUI

/// DINCR Owner identity (the single Owner account and its personal layer, JARVIS).
///
/// The Owner is not a plan: DESIGN.md's "plans don't repaint the app" still holds for Free, Basic and
/// VIP. The Owner's screens keep DINCR's structure, type and components and change only the scene: the
/// platform's own look, a flat grouped background, plain surfaces without borders and one blue accent
/// (DESIGN.md → Owner identity). Light and dark both exist, because DINCR follows the system
/// appearance, and keep WCAG AA (≥ 4.5:1) for text on every Owner surface.
///
/// Screens never read these directly to decide *whether* they are the Owner's: the root sets
/// `dincrOwnerAppearance` from the server role, and the shared modifiers and components read it.
public enum OwnerColor {
    /// The screen background: one flat color (the stops stay so both apps read the same tokens).
    public static let backgroundCenter = Color(light: 0xF2F2F7, dark: 0x000000)
    public static let backgroundMiddle = Color(light: 0xF2F2F7, dark: 0x000000)
    public static let backgroundEdge = Color(light: 0xF2F2F7, dark: 0x000000)
    /// Cards and grouped rows.
    public static let surface = Color(light: 0xFFFFFF, dark: 0x1C1C1E)
    /// Nested regions inside a surface: icon wells, fields.
    public static let surface2 = Color(light: 0xEFEFF4, dark: 0x2C2C2E)
    /// Hairline around Owner surfaces (decorative only; never the only boundary of a control).
    public static let border = Color(light: 0xD1D1D6, dark: 0x38383A)
    /// The Owner accent: actions, links, selection, JARVIS.
    public static let accent = Color(light: 0x0066CC, dark: 0x2997FF)
    /// Pressed / active state of the accent.
    public static let accentActive = Color(light: 0x0055AA, dark: 0x64B0FF)
    public static let onAccent = Color(light: 0xFFFFFF, dark: 0x000000)
    /// Tonal container of the accent: secondary buttons, quick actions, icon wells.
    public static let accentContainer = Color(light: 0xE3EFFC, dark: 0x0B2A4A)
    public static let onAccentContainer = Color(light: 0x003D7A, dark: 0xBFDFFF)
    public static let positive = Color(light: 0x08734F, dark: 0x30D158)
    public static let text = Color(light: 0x1C1C1E, dark: 0xF5F5F7)
    public static let text2 = Color(light: 0x4F4F55, dark: 0xAEAEB2)
    public static let textMuted = Color(light: 0x636366, dark: 0xA1A1A6)
    /// Chart series beyond income/expense. Color always repeats a meaning that is also in text.
    public static let chartCyan = Color(light: 0x0066CC, dark: 0x2997FF)
    public static let chartGreen = Color(light: 0x08734F, dark: 0x30D158)
    public static let chartOrange = Color(light: 0xB4501F, dark: 0xFF855C)
    public static let chartPurple = Color(light: 0x7A45C2, dark: 0xB078F2)
}

/// A role of the shared screens that follows the root's appearance: the Owner's scene below the Owner
/// root, DINCR's own colors everywhere else, so a shared screen needs no Owner branch of its own.
public struct DincrRoleStyle: ShapeStyle {
    let regular: Color
    let owner: Color

    public func resolve(in environment: EnvironmentValues) -> Color.Resolved {
        (environment.dincrOwnerAppearance ? owner : regular).resolve(in: environment)
    }
}

public extension ShapeStyle where Self == DincrRoleStyle {
    static var dincrText: DincrRoleStyle { DincrRoleStyle(regular: DincrColor.text, owner: OwnerColor.text) }
    static var dincrText2: DincrRoleStyle { DincrRoleStyle(regular: DincrColor.text2, owner: OwnerColor.text2) }
    static var dincrTextMuted: DincrRoleStyle { DincrRoleStyle(regular: DincrColor.textMuted, owner: OwnerColor.textMuted) }
    static var dincrTint: DincrRoleStyle { DincrRoleStyle(regular: DincrColor.tint, owner: OwnerColor.accent) }
}

/// Owner shapes: one card radius, one control radius.
public enum OwnerRadius {
    public static let card: CGFloat = 16
    public static let control: CGFloat = 12
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

/// The Owner's screen background: one flat color, in both schemes.
public struct OwnerBackground: View {
    public init() {}

    public var body: some View {
        OwnerColor.backgroundMiddle
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
    }
}

/// The separator between rows of an `OwnerGroup`: a hairline that starts at the row's text.
public struct OwnerDivider: View {
    @Environment(\.displayScale) private var scale
    let inset: CGFloat

    /// `inset`: where the row's text starts (40 after a symbol, 0 in rows without one).
    public init(inset: CGFloat = 40) {
        self.inset = inset
    }

    public var body: some View {
        Rectangle().fill(OwnerColor.border).frame(height: 1 / max(scale, 1))
            .padding(.leading, inset)
            .accessibilityHidden(true)
    }
}

/// One row of an Owner group: a symbol, a title, an optional detail, an optional
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
                .font(.body)
                .foregroundStyle(iconColor)
                .frame(width: 28)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(DincrFont.body).foregroundStyle(OwnerColor.text)
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
            Text(title).font(.title3.weight(.semibold)).foregroundStyle(OwnerColor.text).accessibilityAddTraits(.isHeader)
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
