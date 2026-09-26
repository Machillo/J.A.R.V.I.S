import DincrCore
import Foundation

/// Build-time configuration, injected through `Config/*.xcconfig` into Info.plist.
/// With no backend configured (or with `-DincrFixtures <scenario>`), the app runs on
/// synthetic fixture data: previews, UI tests and screenshots never touch real accounts.
struct AppEnvironment {
    enum Mode {
        case live(apiURL: URL, supabaseURL: URL, anonKey: String)
        case fixtures(FixtureDincrService.Scenario)
    }

    /// The prototype's own redirect, so it can never receive (or steal) the store app's
    /// `com.dincr.app://auth/callback`. Live sign-in needs this URL in Supabase Auth → Redirect
    /// URLs (external gate, native/README.md).
    static let authCallbackScheme = "com.dincr.app.nativedev"
    static let authRedirect = "com.dincr.app.nativedev://auth/callback"

    let mode: Mode

    static func current(bundle: Bundle = .main, arguments: [String] = ProcessInfo.processInfo.arguments) -> AppEnvironment {
        // Launch-argument fixtures are a Debug (UI test) switch only: a release build with a
        // backend configured can never be pointed at sample data.
        if Self.allowsLaunchFixtures, let index = arguments.firstIndex(of: "-DincrFixtures") {
            let raw = arguments.indices.contains(index + 1) ? arguments[index + 1] : "populated"
            return AppEnvironment(mode: .fixtures(FixtureDincrService.Scenario(rawValue: raw) ?? .populated))
        }
        let value = { (key: String) -> String? in
            let text = (bundle.object(forInfoDictionaryKey: key) as? String)?.trimmingCharacters(in: .whitespaces) ?? ""
            return text.isEmpty || text.hasPrefix("$(") ? nil : text
        }
        guard let api = value("DINCRApiURL").flatMap(URL.init(string:)),
              let supabase = value("DINCRSupabaseURL").flatMap(URL.init(string:)),
              let key = value("DINCRSupabaseAnonKey") else {
            return AppEnvironment(mode: .fixtures(.populated))
        }
        return AppEnvironment(mode: .live(apiURL: api, supabaseURL: supabase, anonKey: key))
    }

    #if DEBUG
    static let allowsLaunchFixtures = true
    #else
    static let allowsLaunchFixtures = false
    #endif

    var isFixtures: Bool {
        if case .fixtures = mode { return true }
        return false
    }
}
