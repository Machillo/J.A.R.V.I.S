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

    /// Supabase already allows this redirect for the Capacitor app (nativeAuth.js).
    static let authCallbackScheme = "com.dincr.app"
    static let authRedirect = "com.dincr.app://auth/callback"

    let mode: Mode

    static func current(bundle: Bundle = .main, arguments: [String] = ProcessInfo.processInfo.arguments) -> AppEnvironment {
        if let index = arguments.firstIndex(of: "-DincrFixtures") {
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

    var isFixtures: Bool {
        if case .fixtures = mode { return true }
        return false
    }
}
