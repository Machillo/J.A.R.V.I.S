import Foundation
import Testing
@testable import DincrCore

/// APP-1 personal appearance on iOS (phase 1: model, catalog and policy; Android: `AppearanceTest.kt`).
@Suite struct AppearanceTests {
    func profile(role: String?) -> Profile {
        Profile(id: 1, role: role, planSelected: true, profileSetupCompleted: true,
                subscription: Profile.Subscription(plan: "vip", status: "active"),
                legal: Profile.Legal(required: false, termsVersion: nil, privacyVersion: nil, acceptedAt: nil))
    }

    let choice = AppearancePreferences(theme: "dark", palette: "arena", accent: "ciruela", textSize: "l", typeface: "editorial", density: "compact", surfaces: "tonal")

    @Test func theClassicSetIsTodaysDincrAndTheOwnerDefaultIsTheOwnerIdentity() {
        #expect(AppearancePreferences.classic == AppearancePreferences(theme: "system", palette: "clasico", accent: "teal", textSize: "m", typeface: "system", density: "comfortable", surfaces: "tonal"))
        #expect(AppearancePreferences.ownerDefault == AppearancePreferences(theme: "system", palette: "oceano", accent: "cian", textSize: "m", typeface: "system", density: "comfortable", surfaces: "outlined"))
    }

    @Test func anIdTheAppCannotDrawBecomesTheDefaultOptionByOption() {
        var stale = choice
        stale.palette = "neon"
        stale.surfaces = "glass"
        var expected = choice
        expected.palette = "oceano"
        expected.surfaces = "outlined"
        #expect(stale.sanitized() == expected)
        #expect(choice.sanitized() == choice)
    }

    @Test func onlyTheOwnerPersonalizes() {
        #expect(AppearancePolicy.isPersonalizable(profile(role: "owner")))
        #expect(AppearancePolicy.effective(profile(role: "owner"), saved: choice) == choice)
        #expect(AppearancePolicy.effective(profile(role: "owner"), saved: nil) == .ownerDefault)
        for role in ["user", "admin", nil] as [String?] {
            #expect(!AppearancePolicy.isPersonalizable(profile(role: role)))
            #expect(AppearancePolicy.effective(profile(role: role), saved: choice) == .classic)
        }
        #expect(AppearancePolicy.effective(nil, saved: choice) == .classic)
    }

    @Test func theWireFormatIsTheBackendsSnakeCase() throws {
        let json = #"{"version":1,"preferences":{"theme":"dark","palette":"arena","accent":"ciruela","text_size":"l","typeface":"editorial","density":"compact","surfaces":"tonal"},"stored":true,"updated_at":"2026-10-22T10:00:00+00:00"}"#
        let state = try APIClient.decoder.decode(AppearanceState.self, from: Data(json.utf8))
        #expect(state.preferences == choice && state.stored)
        let body = try #require(String(data: try APIClient.encoder.encode(choice), encoding: .utf8))
        #expect(body.contains(#""text_size":"l""#))
    }
}
