import Foundation

/// A personal appearance (APP-1): one closed id per option of the shared catalog
/// (`design-tokens/appearance.json` → `AppearanceCatalog`). The backend accepts exactly these ids
/// (`/user-product/appearance`); Android: `com.dincr.data.AppearancePrefs`.
///
/// Phase 1 on iOS ships this model, the catalog, the tokens and the API calls only. The
/// Personalización screen and the theming are not wired yet (MAC REQUIRED); until then the iOS
/// Owner keeps its Owner scene, which is the Owner default (Océano + Cian, outlined surfaces).
public struct AppearancePreferences: Codable, Sendable, Equatable {
    public var theme: String
    public var palette: String
    public var accent: String
    public var textSize: String
    public var typeface: String
    public var density: String
    public var surfaces: String

    public init(theme: String, palette: String, accent: String, textSize: String, typeface: String, density: String, surfaces: String) {
        self.theme = theme; self.palette = palette; self.accent = accent; self.textSize = textSize
        self.typeface = typeface; self.density = density; self.surfaces = surfaces
    }

    public func id(_ key: String) -> String? {
        switch key {
        case "theme": theme
        case "palette": palette
        case "accent": accent
        case "text_size": textSize
        case "typeface": typeface
        case "density": density
        case "surfaces": surfaces
        default: nil
        }
    }

    /// The same choice with one option changed.
    public func with(_ key: String, _ id: String) -> AppearancePreferences {
        var copy = self
        switch key {
        case "theme": copy.theme = id
        case "palette": copy.palette = id
        case "accent": copy.accent = id
        case "text_size": copy.textSize = id
        case "typeface": copy.typeface = id
        case "density": copy.density = id
        case "surfaces": copy.surfaces = id
        default: break
        }
        return copy
    }

    /// Every option a catalog id; one the app can't draw (an old cache, a newer server) becomes the default.
    public func sanitized() -> AppearancePreferences {
        AppearanceCatalog.options.reduce(self) { prefs, option in
            option.has(prefs.id(option.key)) ? prefs : prefs.with(option.key, option.defaultValue)
        }
    }

    private static func from(_ pick: (AppearanceOption) -> String) -> AppearancePreferences {
        AppearanceCatalog.options.reduce(AppearancePreferences(theme: "", palette: "", accent: "", textSize: "", typeface: "", density: "", surfaces: "")) {
            $0.with($1.key, pick($1))
        }
    }

    /// The Owner's starting point (the Owner identity).
    public static let ownerDefault = from { $0.defaultValue }
    /// Today's DINCR, exactly (DESIGN.md): what every account that does not personalize sees.
    public static let classic = from { $0.classic }
}

/// `GET/PUT/DELETE /user-product/appearance`.
public struct AppearanceState: Decodable, Sendable, Equatable {
    public let version: Int
    public let preferences: AppearancePreferences
    public let stored: Bool
    public let updatedAt: String?
}

/// Who personalizes and what each account sees (APP-1, phase 1: the Owner only). The backend refuses
/// the routes to everyone else; this keeps the app from drawing anything but the classic look for them.
public enum AppearancePolicy {
    public static func isPersonalizable(_ profile: Profile?) -> Bool { profile?.isOwner == true }

    public static func effective(_ profile: Profile?, saved: AppearancePreferences?) -> AppearancePreferences {
        guard isPersonalizable(profile) else { return .classic }
        return saved?.sanitized() ?? .ownerDefault
    }
}
