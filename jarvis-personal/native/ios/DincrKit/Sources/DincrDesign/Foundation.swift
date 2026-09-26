import SwiftUI

#if canImport(UIKit)
import UIKit
#endif

extension Color {
    /// A color that follows the system appearance (and the in-app override applied through
    /// `preferredColorScheme`). Values come from the generated DESIGN.md tokens.
    init(light: UInt32, dark: UInt32) {
        #if canImport(UIKit)
        self.init(uiColor: UIColor { traits in
            UIColor(rgb: traits.userInterfaceStyle == .dark ? dark : light)
        })
        #else
        self.init(nsColor: NSColor(name: nil) { appearance in
            let isDark = appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
            let value = isDark ? dark : light
            return NSColor(srgbRed: CGFloat((value >> 16) & 0xFF) / 255, green: CGFloat((value >> 8) & 0xFF) / 255, blue: CGFloat(value & 0xFF) / 255, alpha: 1)
        })
        #endif
    }
}

#if canImport(UIKit)
extension UIColor {
    convenience init(rgb: UInt32) {
        self.init(red: CGFloat((rgb >> 16) & 0xFF) / 255, green: CGFloat((rgb >> 8) & 0xFF) / 255, blue: CGFloat(rgb & 0xFF) / 255, alpha: 1)
    }
}
#endif

/// DINCR type roles (DESIGN.md → Typography). All are system text styles, so they follow
/// Dynamic Type up to the accessibility sizes.
public enum DincrFont {
    /// The one key figure per screen. Tabular digits.
    public static let displayAmount = Font.largeTitle.weight(.bold).monospacedDigit()
    public static let title1 = Font.title2.weight(.bold)
    public static let title2 = Font.headline
    public static let body = Font.body
    public static let bodySmall = Font.subheadline
    public static let label = Font.footnote.weight(.medium)
    public static let caption = Font.caption
    /// Money inside rows and cards: tabular so columns align.
    public static let amount = Font.body.weight(.semibold).monospacedDigit()
}

private struct DecorativeMotionKey: EnvironmentKey {
    static let defaultValue = true
}

public extension EnvironmentValues {
    /// Off in UI tests (and anywhere a looping animation must not run); Reduce Motion also stops it.
    var dincrDecorativeMotion: Bool {
        get { self[DecorativeMotionKey.self] }
        set { self[DecorativeMotionKey.self] = newValue }
    }
}

/// Motion tokens (DESIGN_SYSTEM.md §5). Callers pass `reduceMotion` from the environment so
/// movement becomes a cross-fade when the user asked for less motion.
public enum DincrMotion {
    public static func quick(_ reduceMotion: Bool) -> Animation { reduceMotion ? .easeInOut(duration: 0.15) : .snappy(duration: 0.2) }
    public static func standard(_ reduceMotion: Bool) -> Animation { reduceMotion ? .easeInOut(duration: 0.15) : .smooth(duration: 0.3) }
}

public extension View {
    /// Card surface: tonal, no shadow (DESIGN.md → Elevation & Depth).
    func dincrCard(padding: CGFloat = DincrSpacing.s4) -> some View {
        self.padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(DincrColor.surface, in: RoundedRectangle(cornerRadius: DincrRadius.lg, style: .continuous))
    }

    /// Screen background.
    func dincrScreenBackground() -> some View {
        background(DincrColor.bg.ignoresSafeArea())
    }
}
