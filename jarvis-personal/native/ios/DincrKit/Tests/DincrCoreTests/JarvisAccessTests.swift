import Foundation
import Testing
@testable import DincrCore

/// JARVIS (recovery roadmap J0): the Owner's personal space. Only the server's role opens it: never
/// a plan, a flag in the payload or a local copy of the profile. Android: `JarvisAccessTest.kt`.
@Suite struct JarvisAccessTests {
    func profile(role: String?, plan: String?) -> Profile {
        Profile(id: 1, role: role, subscription: plan.map { Profile.Subscription(plan: $0, status: "active") })
    }

    @Test func onlyTheOwnerGetsJarvis() {
        // Free, Basic and VIP accounts never get it.
        for plan in ["free", "basic", "vip", nil] as [String?] {
            #expect(!Jarvis.isAvailable(to: profile(role: "user", plan: plan)))
        }
        // The Owner does, whatever its stored plan code.
        for plan in ["vip", "owner", "free", nil] as [String?] {
            #expect(Jarvis.isAvailable(to: profile(role: "owner", plan: plan)))
        }
        // Admin is not the Owner; no identity (signed out, still loading) gets nothing.
        #expect(!Jarvis.isAvailable(to: profile(role: "admin", plan: "vip")))
        #expect(!Jarvis.isAvailable(to: nil))
    }

    @Test func theOwnerKeepsEveryDincrScreen() {
        // JARVIS is added on top of the public app: the Owner still enters it at VIP level.
        let owner = profile(role: "owner", plan: "vip")
        #expect(IdentityGate.of(owner) == .ready)
        #expect(owner.planTier == .vip)
        #expect(Feature.allCases.allSatisfy { owner.planTier.allows($0) })
        // …and admin still stays out of the public app.
        #expect(IdentityGate.of(profile(role: "admin", plan: "vip")) == .internalOnly)
    }

    @Test func noClientStateOpensJarvis() throws {
        // Plan codes, look-alike roles and extra flags in the payload never elevate.
        for json in [
            #"{"id":1,"role":"user","subscription":{"plan":"owner","access_source":"owner"}}"#,
            #"{"id":1,"role":"user","is_owner":true,"jarvis":true,"owner":true}"#,
            #"{"id":1,"role":"Owner"}"#, #"{"id":1,"role":" owner"}"#, #"{"id":1,"role":"OWNER"}"#,
            #"{"id":1}"#,
        ] {
            let decoded = try APIClient.decoder.decode(Profile.self, from: Data(json.utf8))
            #expect(!Jarvis.isAvailable(to: decoded), "\(json)")
        }
        // The role is server data: copies of a profile keep it.
        let user = profile(role: "user", plan: "vip")
        #expect(!Jarvis.isAvailable(to: user.with(planSelected: true, subscription: .init(plan: "owner", status: "active"))))
    }

    @Test func theChatAndTheAgendaAreThePortedSections() {
        // J1 ports the chat and J2 the agenda; every other section still opens a "being restored" screen.
        #expect(Jarvis.Section.allCases.filter(\.isAvailable) == [.chat, .calendar])
        // The same sections and wire names as Android (`Jarvis.Section`).
        #expect(Jarvis.Section.allCases.map(\.rawValue) == ["chat", "memory", "calendar", "strategy", "money", "money_control", "wealth", "records"])
    }

    @Test func theFixtureServerDecidesTheRole() async throws {
        // What the app knows about the role comes from /auth/me, as with the real backend.
        let owner = try await FixtureBackend.service(FixtureBackend(role: .owner, latency: .zero)).me()
        #expect(owner.isOwner && Jarvis.isAvailable(to: owner))
        #expect(owner.subscription?.plan == "vip" && owner.subscription?.accessSource == "owner")
        let admin = try await FixtureBackend.service(FixtureBackend(plan: .vip, role: .admin, latency: .zero)).me()
        #expect(!Jarvis.isAvailable(to: admin) && IdentityGate.of(admin) == .internalOnly)
        for plan in [PlanTier.free, .basic, .vip] {
            let user = try await FixtureBackend.service(FixtureBackend(plan: plan, latency: .zero)).me()
            #expect(user.role == "user" && !Jarvis.isAvailable(to: user))
        }
    }
}
