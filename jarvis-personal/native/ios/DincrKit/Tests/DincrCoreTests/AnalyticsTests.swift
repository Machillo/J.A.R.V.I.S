import Foundation
import Testing
@testable import DincrCore

/// Product analytics contract v2 on the native app: closed-list events through the backend relay,
/// an anonymous install ID, nothing before the identity is ready. Android: `AnalyticsTest.kt`;
/// parity with the Capacitor contract: `backend/product_ops/test_analytics_relay.py`.
@Suite struct AnalyticsTests {
    actor Sent {
        var events: [AnalyticsEvent] = []
        func add(_ event: AnalyticsEvent) { events.append(event) }
    }

    final class Clock: @unchecked Sendable {
        var now = Date(timeIntervalSince1970: 0)
    }

    func make(_ sent: Sent, clock: Clock = Clock()) -> NativeAnalytics {
        let defaults = UserDefaults(suiteName: "analytics-tests-\(UUID().uuidString)")!
        return NativeAnalytics(defaults: defaults, version: "2.0.0-rc.1", build: "release", clock: { clock.now }) { event in
            await sent.add(event)
        }
    }

    func settle(_ analytics: NativeAnalytics) async { await analytics.pending?.value }

    @Test func nothingIsSentUntilEnabled() async {
        let sent = Sent()
        let analytics = make(sent)
        await analytics.screen("home")
        await analytics.writeSucceeded(method: "POST", path: "/user-product/goals")
        await settle(analytics)
        #expect(await sent.events.isEmpty)
    }

    @Test func eventsCarryOnlyClosedValuesAndAnAnonymousInstallID() async {
        let sent = Sent()
        let analytics = make(sent)
        await analytics.setEnabled(true); await settle(analytics)
        await analytics.screen("movements"); await settle(analytics)
        await analytics.screen("unknown_screen"); await settle(analytics)
        await analytics.jarvisSection(.calendar); await settle(analytics)
        let events = await sent.events
        #expect(events.map(\.event) == ["app_opened", "screen_viewed", "jarvis_section_viewed"])
        #expect(events[1].properties == ["screen": "transactions"])
        #expect(events[2].properties == ["jarvis_section": "calendar"])
        let installID = events[0].installId
        #expect(installID.range(of: #"^[0-9a-f-]{36}$"#, options: .regularExpression) != nil)
        for event in events {
            #expect(event.installId == installID && event.platform == "ios" && event.appVersion == "2.0.0" && event.build == "release")
            #expect(AnalyticsContract.events.contains(event.event))
            for (name, value) in event.properties {
                #expect(["screen", "jarvis_section", "action_type"].contains(name))
                #expect(value.range(of: #"^[a-z_-]+$"#, options: .regularExpression) != nil)
            }
        }
    }

    @Test func usefulActionsAreTypesOfSuccessfulWritesNeverPaths() async {
        let sent = Sent()
        let analytics = make(sent)
        await analytics.setEnabled(true); await settle(analytics)
        await analytics.writeSucceeded(method: "PUT", path: "/user-product/financial-situation"); await settle(analytics)
        await analytics.writeSucceeded(method: "POST", path: "/user-product/goals/7/contributions?x=1"); await settle(analytics)
        await analytics.writeSucceeded(method: "GET", path: "/user-product/goals"); await settle(analytics)
        await analytics.writeSucceeded(method: "POST", path: "/product-ops/analytics"); await settle(analytics)
        let events = await sent.events.dropFirst()
        #expect(events.map(\.event) == ["financial_profile_saved", "useful_action", "useful_action"])
        #expect(events.compactMap { $0.properties["action_type"] } == ["financial_profile_saved", "goal_contribution_recorded"])
        #expect(events.allSatisfy { !$0.properties.values.contains { $0.contains("/") } })
    }

    @Test func signOutRotatesTheInstallIDAndStops() async {
        let sent = Sent()
        let analytics = make(sent)
        await analytics.setEnabled(true); await settle(analytics)
        let first = await sent.events[0].installId
        await analytics.reset()
        await analytics.screen("home"); await settle(analytics)
        #expect(await sent.events.count == 1)
        await analytics.setEnabled(true); await settle(analytics)
        #expect(await sent.events.last?.installId != first)
    }

    @Test func aSessionEndsAfterThirtyIdleMinutes() async {
        let sent = Sent()
        let clock = Clock()
        let analytics = make(sent, clock: clock)
        await analytics.setEnabled(true); await settle(analytics)
        clock.now += 29 * 60
        await analytics.screen("home"); await settle(analytics)
        clock.now += 31 * 60
        await analytics.screen("home"); await settle(analytics)
        let events = await sent.events
        #expect(events[0].sessionId == events[1].sessionId)
        #expect(events[1].sessionId != events[2].sessionId)
    }

    @Test func appVersionIsXyzOnly() {
        #expect(AnalyticsContract.appVersion("2.0.0-rc.1") == "2.0.0")
        #expect(AnalyticsContract.appVersion("dev") == nil)
    }

    @Test func theRelayBodyIsSnakeCaseWithNoOtherFields() throws {
        let event = AnalyticsEvent(event: "screen_viewed", properties: ["screen": "overview"], installId: "x", sessionId: nil,
                                   platform: "ios", appVersion: "2.0.0", build: "release")
        let json = try JSONSerialization.jsonObject(with: APIClient.encoder.encode(event)) as? [String: Any]
        #expect(Set((json ?? [:]).keys) == ["event", "properties", "install_id", "platform", "app_version", "build"])
        #expect((json?["properties"] as? [String: String]) == ["screen": "overview"])
    }
}
