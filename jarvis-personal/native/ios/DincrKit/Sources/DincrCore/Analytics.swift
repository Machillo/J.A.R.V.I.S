import Foundation

/// Product analytics contract v2 for the native app (docs/analytics/posthog-event-taxonomy.md).
///
/// The native app has no PostHog SDK and no PostHog key: it sends closed-list events to
/// `POST /product-ops/analytics`, and the backend checks them against the same contract as the
/// Capacitor app, decides the audience (Users / Owner / nothing) from its own records and relays
/// them to PostHog. Only fixed names and categories leave the device: never an amount, a name, an
/// email, a bank or account, chat or calendar content, free text or an internal identifier.
/// Parity with `frontend/src/lib/analyticsContract.js` is checked by `test_analytics_relay.py`.
public enum AnalyticsContract {
    /// Every event this app sends (a subset of the v2 contract).
    public static let events: Set<String> = [
        "app_opened", "screen_viewed", "useful_action", "financial_profile_saved",
        "jarvis_opened", "jarvis_section_viewed",
    ]

    /// Native screen name → contract `screen` value.
    public static let screens: [String: String] = [
        "home": "overview", "movements": "transactions", "plan": "plan", "advisor": "advisor",
        "profile": "profile", "mail": "gmail",
    ]

    public struct Rule: Sendable {
        public let method: String
        public let pattern: String
        public let actionType: String
    }

    /// Same rules, in the same order, as `usefulActionRules` in analyticsContract.js.
    public static let usefulActionRules: [Rule] = [
        Rule(method: "PUT", pattern: #"^/user-product/financial-situation$"#, actionType: "financial_profile_saved"),
        Rule(method: "POST", pattern: #"^/user-product/finance/income$"#, actionType: "income_added"),
        Rule(method: "PUT", pattern: #"^/user-product/finance/income/[^/]+$"#, actionType: "income_updated"),
        Rule(method: "POST", pattern: #"^/user-product/finance/expenses$"#, actionType: "expense_added"),
        Rule(method: "PUT", pattern: #"^/user-product/finance/expenses/[^/]+$"#, actionType: "expense_updated"),
        Rule(method: "POST", pattern: #"^/user-product/finance/debts$"#, actionType: "debt_added"),
        Rule(method: "PUT", pattern: #"^/user-product/finance/debts/[^/]+$"#, actionType: "debt_updated"),
        Rule(method: "POST", pattern: #"^/user-product/finance/debts/[^/]+/payments$"#, actionType: "debt_payment_recorded"),
        Rule(method: "PUT", pattern: #"^/user-product/vip/salvavidas$"#, actionType: "salvavidas_saved"),
        Rule(method: "POST", pattern: #"^/user-product/goals$"#, actionType: "goal_created"),
        Rule(method: "PUT", pattern: #"^/user-product/goals/[^/]+$"#, actionType: "goal_updated"),
        Rule(method: "POST", pattern: #"^/user-product/goals/[^/]+/contributions$"#, actionType: "goal_contribution_recorded"),
        Rule(method: "POST", pattern: #"^/user-product/savings-plans$"#, actionType: "savings_plan_created"),
        Rule(method: "PUT", pattern: #"^/user-product/savings-plans/[^/]+$"#, actionType: "savings_plan_updated"),
        Rule(method: "POST", pattern: #"^/user-product/savings-plans/[^/]+/contributions$"#, actionType: "savings_contribution_recorded"),
        Rule(method: "POST", pattern: #"^/user-product/transactions$"#, actionType: "transaction_added"),
        Rule(method: "PUT", pattern: #"^/user-product/free/movements/[^/]+$"#, actionType: "transaction_updated"),
        Rule(method: "PUT", pattern: #"^/user-product/basic/budget$"#, actionType: "budget_saved"),
        Rule(method: "POST", pattern: #"^/user-product/basic/recurring$"#, actionType: "recurring_added"),
        Rule(method: "PUT", pattern: #"^/user-product/basic/recurring/[^/]+$"#, actionType: "recurring_updated"),
    ]

    /// The action type of a successful write, or nil. The path itself never leaves the device.
    public static func usefulAction(method: String, path: String) -> String? {
        var clean = String(path.split(separator: "?", maxSplits: 1, omittingEmptySubsequences: false).first ?? "")
        clean = String(clean.split(separator: "#", maxSplits: 1, omittingEmptySubsequences: false).first ?? "")
        while clean.hasSuffix("/") { clean.removeLast() }
        let verb = method.uppercased()
        return usefulActionRules.first { rule in
            rule.method == verb && clean.range(of: rule.pattern, options: .regularExpression) != nil
        }?.actionType
    }

    /// `x.y.z` only (a pre-release suffix such as `-rc.1` is dropped), or nil.
    public static func appVersion(_ version: String) -> String? {
        guard let range = version.range(of: #"^\d+\.\d+\.\d+"#, options: .regularExpression) else { return nil }
        return String(version[range])
    }
}

/// `POST /product-ops/analytics`: one native event (encoded snake_case by `APIClient`).
public struct AnalyticsEvent: Encodable, Sendable, Equatable {
    public let event: String
    public let properties: [String: String]
    public let installId: String
    public let sessionId: String?
    public let platform: String
    public let appVersion: String?
    public let build: String
}

/// The native app's product analytics. Off until `setEnabled(true)` (identity ready, live backend).
///
/// Identity is a random install UUID: the native equivalent of posthog-js's anonymous device ID.
/// It is rotated on sign-out, so two accounts on one phone are never joined, and it is never
/// derived from an account, an email or any other identifier.
public actor NativeAnalytics {
    public static let installIDKey = "dincr.analytics.installID"
    static let sessionIdle: TimeInterval = 30 * 60

    private let defaults: UserDefaults
    private let appVersion: String?
    private let build: String
    private let clock: @Sendable () -> Date
    private let send: @Sendable (AnalyticsEvent) async throws -> Void
    private var enabled = false
    private var sessionID: String?
    private var lastEventAt = Date.distantPast

    public init(
        defaults: UserDefaults = .standard, version: String, build: String,
        clock: @escaping @Sendable () -> Date = { Date() },
        send: @escaping @Sendable (AnalyticsEvent) async throws -> Void
    ) {
        self.defaults = defaults
        self.appVersion = AnalyticsContract.appVersion(version)
        self.build = build
        self.clock = clock
        self.send = send
    }

    /// Sends through the backend relay with its own client, so the relay never reports itself.
    public static func relay(_ client: APIClient) -> @Sendable (AnalyticsEvent) async throws -> Void {
        { event in let _: Acknowledgement = try await client.send("POST", "/product-ops/analytics", body: event) }
    }

    public var isEnabled: Bool { enabled }

    /// Turns analytics on when the identity becomes ready (sending `app_opened` once) and off otherwise.
    public func setEnabled(_ on: Bool) async {
        let wasOn = enabled
        enabled = on
        if on, !wasOn { await record("app_opened") }
    }

    /// A Users screen, by its native name; unknown names are not sent.
    public func screen(_ nativeName: String) async {
        guard let screen = AnalyticsContract.screens[nativeName] else { return }
        await record("screen_viewed", ["screen": screen])
    }

    public func jarvisOpened() async { await record("jarvis_opened") }

    public func jarvisSection(_ section: Jarvis.Section) async {
        await record("jarvis_section_viewed", ["jarvis_section": section.rawValue])
    }

    /// Called after every successful write; only matching writes are sent.
    public func writeSucceeded(method: String, path: String) async {
        guard let action = AnalyticsContract.usefulAction(method: method, path: path) else { return }
        if action == "financial_profile_saved" { await record("financial_profile_saved") }
        await record("useful_action", ["action_type": action])
    }

    /// A hook for `APIClient(onSuccessfulWrite:)`.
    public nonisolated var writeHook: @Sendable (String, String) -> Void {
        { [weak self] method, path in Task { await self?.writeSucceeded(method: method, path: path) } }
    }

    /// Sign-out: stop, and start the next account with a new anonymous install ID.
    public func reset() {
        enabled = false
        sessionID = nil
        defaults.removeObject(forKey: Self.installIDKey)
    }

    private func record(_ name: String, _ properties: [String: String] = [:]) async {
        guard enabled, AnalyticsContract.events.contains(name) else { return }
        let installID: String
        if let stored = defaults.string(forKey: Self.installIDKey) {
            installID = stored
        } else {
            installID = UUID().uuidString.lowercased()
            defaults.set(installID, forKey: Self.installIDKey)
        }
        let now = clock()
        if sessionID == nil || now.timeIntervalSince(lastEventAt) > Self.sessionIdle { sessionID = UUID().uuidString.lowercased() }
        lastEventAt = now
        let event = AnalyticsEvent(
            event: name, properties: properties, installId: installID, sessionId: sessionID,
            platform: "ios", appVersion: appVersion, build: build
        )
        // Analytics never blocks or breaks the app (nor this actor while a request is in flight);
        // sends go out one after another, in the order they were recorded.
        let send = self.send
        let previous = pending
        pending = Task {
            await previous?.value
            try? await send(event)
        }
    }

    /// The last send in flight (tests await it).
    public private(set) var pending: Task<Void, Never>?
}
