import Foundation
import Testing
@testable import DincrCore

/// Where a signed-in identity lands in the public app, and what it offers. The server decides the
/// role and the plan; the app only routes (Android: `OwnerAccessTest.kt`).
@Suite struct OwnerAccessTests {
    func profile(role: String?, plan: String?, planSelected: Bool? = true, profileSetup: Bool? = true, legalRequired: Bool = false) -> Profile {
        Profile(id: 1, role: role, planSelected: planSelected, profileSetupCompleted: profileSetup,
                subscription: plan.map { Profile.Subscription(plan: $0, status: "active") },
                legal: Profile.Legal(required: legalRequired, termsVersion: nil, privacyVersion: nil, acceptedAt: nil))
    }

    @Test func freeBasicAndVipEnterTheirOwnExperience() {
        for (plan, tier) in [("free", PlanTier.free), ("basic", .basic), ("vip", .vip)] {
            let user = profile(role: "user", plan: plan)
            #expect(IdentityGate.of(user) == .ready)
            #expect(user.planTier == tier)
        }
    }

    @Test func ownerEntersThePublicAppWithAtLeastVip() {
        // Whatever the stored plan code (the backend seeds Owner as vip with access_source owner).
        for plan in ["vip", "owner", "free", nil] as [String?] {
            let owner = profile(role: "owner", plan: plan, planSelected: false)
            #expect(IdentityGate.of(owner) == .ready, "Owner's plan is granted by the backend, never chosen")
            #expect(owner.planTier == .vip)
            #expect(Feature.allCases.allSatisfy { owner.planTier.allows($0) })
        }
        // Owner still goes through the legal and profile steps like anyone else.
        #expect(IdentityGate.of(profile(role: "owner", plan: "vip", legalRequired: true)) == .legalRequired)
        #expect(IdentityGate.of(profile(role: "owner", plan: "vip", profileSetup: false)) == .profileSetup)
    }

    @Test func ownerGetsNoInternalScreens() {
        // The public app has no tier above VIP and no internal feature: Owner sees exactly VIP.
        #expect(PlanTier.allCases == [.free, .basic, .vip])
        let owner = profile(role: "owner", plan: "owner")
        #expect(Feature.allCases.filter { owner.planTier.allows($0) } == Feature.allCases.filter { PlanTier.vip.allows($0) })
        // Admin sessions stay out of the public app, as before.
        #expect(IdentityGate.of(profile(role: "admin", plan: "vip")) == .unsupportedRole)
        #expect(!profile(role: "admin", plan: "vip").isOwner)
    }

    @Test func theOwnerAccountIsNeverDeletedFromThePublicApp() {
        // DELETE /auth/me has no Owner guard on the server; the public app never offers it to Owner.
        #expect(!profile(role: "owner", plan: "vip").canDeleteAccountInApp)
        for plan in ["free", "basic", "vip"] { #expect(profile(role: "user", plan: plan).canDeleteAccountInApp) }
    }

    @Test func noClientPathTurnsAUserIntoOwner() throws {
        // A plan code alone never elevates: only the server's role does.
        let user = profile(role: "user", plan: "owner")
        #expect(!user.isOwner && user.planTier == .free)
        #expect(PlanTier.from("owner") == .free)
        // The role is read-only: copies keep it, and a missing role is not Owner.
        #expect(user.with(planSelected: true, subscription: .init(plan: "vip", status: "active")).role == "user")
        let unknown = try APIClient.decoder.decode(Profile.self, from: Data(#"{"id":1,"subscription":{"plan":"owner"}}"#.utf8))
        #expect(!unknown.isOwner && unknown.planTier == .free)
        // The plans a user can pick never include Owner.
        #expect(!PlanTier.allCases.map(\.rawValue).contains("owner"))
    }
}
