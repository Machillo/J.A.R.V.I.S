import Foundation

/// Decides how the prototype starts. Same rules as Android `LaunchPolicy`:
///
/// - Fixture (sample) data only in a Debug build, and only when asked for explicitly (the UI
///   tests' `-DincrFixtures` launch argument). A Release build never runs on fixtures, whatever
///   it is launched with.
/// - Otherwise the backend must be configured completely, over HTTPS. A Debug build may use plain
///   HTTP on the developer's own machine (loopback) only.
/// - Anything else is `.unconfigured`: the app says so and stops. It never falls back to
///   fixtures silently, so sample figures can never be mistaken for a real account.
public enum LaunchPolicy {
    public enum Reason: Equatable, Sendable { case missing, insecureURL, invalidURL }

    public enum Decision: Equatable, Sendable {
        case live(apiURL: URL, supabaseURL: URL, anonKey: String)
        case fixtures(scenario: String?)
        case unconfigured(Reason)
    }

    static let developmentHosts: Set<String> = ["localhost", "127.0.0.1", "::1", "[::1]"]

    public static func decide(
        debugBuild: Bool, launchFixtures: String?, apiURL: String?, supabaseURL: String?, anonKey: String?
    ) -> Decision {
        if debugBuild, let launchFixtures { return .fixtures(scenario: launchFixtures.isEmpty ? nil : launchFixtures) }
        let trimmed = { (value: String?) in (value ?? "").trimmingCharacters(in: .whitespaces) }
        let api = trimmed(apiURL), supabase = trimmed(supabaseURL), key = trimmed(anonKey)
        // xcconfig leaves "$(NAME)" when a value is not set.
        guard !api.isEmpty, !supabase.isEmpty, !key.isEmpty, ![api, supabase, key].contains(where: { $0.hasPrefix("$(") }) else {
            return .unconfigured(.missing)
        }
        var urls: [URL] = []
        for text in [api, supabase] {
            guard let components = URLComponents(string: text), let host = components.host, !host.isEmpty,
                  components.user == nil, components.password == nil,
                  (components.query ?? "").isEmpty, (components.fragment ?? "").isEmpty,
                  let url = components.url else {
                return .unconfigured(.invalidURL)
            }
            let scheme = components.scheme?.lowercased()
            let secure = scheme == "https" || (debugBuild && scheme == "http" && developmentHosts.contains(host.lowercased()))
            guard secure else { return .unconfigured(.insecureURL) }
            urls.append(url)
        }
        return .live(apiURL: urls[0], supabaseURL: urls[1], anonKey: key)
    }
}
