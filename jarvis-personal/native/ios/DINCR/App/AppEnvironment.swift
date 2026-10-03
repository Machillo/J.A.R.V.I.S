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
        case fixtures(FixtureBackend.Scenario, PlanTier, FixtureBackend.Role)
        case unconfigured(LaunchPolicy.Reason)
    }

    /// The release identity's OAuth return (`AppIdentity`, pinned by tests).
    static let authCallbackScheme = AppIdentity.authCallbackScheme
    static let authRedirect = AppIdentity.authRedirect

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
            // `-DincrPlan basic|vip` picks the fixture account's plan (UI tests of plan gates), and
            // `-DincrRole owner` (or the legacy value `admin`, to prove it is refused) the role the fake server answers in /auth/me (role matrix).
            // Fixtures only: a live session's role always comes from the real backend.
            let argument = { (flag: String) in arguments.firstIndex(of: flag).flatMap { arguments.indices.contains($0 + 1) ? arguments[$0 + 1] : nil } }
            return AppEnvironment(mode: .fixtures(scenario.flatMap(FixtureBackend.Scenario.init(rawValue:)) ?? .populated, PlanTier.from(argument("-DincrPlan")),
                                                  argument("-DincrRole").flatMap(FixtureBackend.Role.init(rawValue:)) ?? .user))
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
