import DincrCore
import Foundation

/// Build-time configuration, injected through `Config/*.xcconfig` into Info.plist and decided by
/// `LaunchPolicy`. Fixture data only in a Debug build launched with `-DincrFixtures <scenario>`
/// (UI tests, screenshots, local demos): a Release build can never be pointed at sample data.
/// Without a complete HTTPS backend configuration the app shows an "unconfigured" screen instead
/// of silently running on fixtures.
struct AppEnvironment {
    enum Mode {
        case live(apiURL: URL, supabaseURL: URL, anonKey: String)
        case fixtures(FixtureDincrService.Scenario, PlanTier)
        case unconfigured(LaunchPolicy.Reason)
    }

    /// The prototype's own redirect, so it can never receive (or steal) the store app's
    /// `com.dincr.app://auth/callback`. Live sign-in needs this URL in Supabase Auth → Redirect
    /// URLs (external gate, native/README.md).
    static let authCallbackScheme = "com.dincr.app.nativedev"
    static let authRedirect = "com.dincr.app.nativedev://auth/callback"

    let mode: Mode

    static func current(bundle: Bundle = .main, arguments: [String] = ProcessInfo.processInfo.arguments) -> AppEnvironment {
        var launchFixtures: String?
        if let index = arguments.firstIndex(of: "-DincrFixtures") {
            launchFixtures = arguments.indices.contains(index + 1) ? arguments[index + 1] : ""
        }
        let value = { (key: String) in bundle.object(forInfoDictionaryKey: key) as? String }
        switch LaunchPolicy.decide(
            debugBuild: isDebugBuild, launchFixtures: launchFixtures,
            apiURL: value("DINCRApiURL"), supabaseURL: value("DINCRSupabaseURL"), anonKey: value("DINCRSupabaseAnonKey")
        ) {
        case let .live(apiURL, supabaseURL, anonKey):
            return AppEnvironment(mode: .live(apiURL: apiURL, supabaseURL: supabaseURL, anonKey: anonKey))
        case let .fixtures(scenario):
            // `-DincrPlan basic|vip` picks the fixture account's plan (UI tests of plan gates).
            let plan = arguments.firstIndex(of: "-DincrPlan").flatMap { arguments.indices.contains($0 + 1) ? arguments[$0 + 1] : nil }
            return AppEnvironment(mode: .fixtures(scenario.flatMap(FixtureDincrService.Scenario.init(rawValue:)) ?? .populated, PlanTier.from(plan)))
        case let .unconfigured(reason):
            return AppEnvironment(mode: .unconfigured(reason))
        }
    }

    #if DEBUG
    static let isDebugBuild = true
    #else
    static let isDebugBuild = false
    #endif

    var isFixtures: Bool {
        if case .fixtures = mode { return true }
        return false
    }
}
