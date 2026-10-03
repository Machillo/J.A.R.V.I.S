import Foundation
import Testing
@testable import DincrCore

/// The plan gates DincrCore decides agree with the shared reachability spec
/// (`native/feature-reachability.json`, master plan R1 / P0.0). The UI reachability itself is
/// walked by `FeatureReachabilityUITests`; Android checks the same spec in `FeatureReachabilitySpecTest.kt`.
@Suite struct FeatureReachabilitySpecTests {
    struct Spec: Decodable {
        struct Feature: Decodable {
            let id: String
            let plans: [String: String]
            let platformStates: [String: [String: String]]?
            let placeholder: String?

            enum CodingKeys: String, CodingKey { case id, plans, placeholder, platformStates = "platform_states" }

            func state(_ plan: String) -> String { platformStates?["ios"]?[plan] ?? plans[plan] ?? "" }
        }
        let features: [Feature]
    }

    static let spec: Spec = {
        // native/ios/DincrKit/Tests/DincrCoreTests/<this file> → native/feature-reachability.json
        var url = URL(fileURLWithPath: #filePath)
        for _ in 0..<5 { url.deleteLastPathComponent() }
        let data = try! Data(contentsOf: url.appendingPathComponent("feature-reachability.json"))
        return try! JSONDecoder().decode(Spec.self, from: data)
    }()

    func feature(_ id: String) -> Spec.Feature {
        guard let found = Self.spec.features.first(where: { $0.id == id }) else { fatalError("spec has no feature \(id)") }
        return found
    }

    @Test func thePlanTabRowsFollowTheSpec() {
        for item in PlanHubItem.allCases {
            let feature = feature("plan.\(item.rawValue)")
            for tier in PlanTier.allCases {
                let expected = feature.state(tier.rawValue)
                switch item.availability(tier: tier, flags: .unknown) {
                case .available, .paused: #expect(expected == "AVAILABLE", "\(item.rawValue) \(tier.rawValue)")
                case .locked: #expect(expected == "VISIBLE_LOCKED", "\(item.rawValue) \(tier.rawValue)")
                }
            }
            #expect(feature.state("owner") == "AVAILABLE")
        }
    }

    @Test func everyPlanTabRowIsInTheSpecAndNothingElse() {
        let specRows = Set(Self.spec.features.map(\.id).filter { $0.hasPrefix("plan.") })
        #expect(specRows == Set(PlanHubItem.allCases.map { "plan.\($0.rawValue)" }))
    }

    @Test func jarvisSectionsAreOwnerOnlyAndPortedOnesAreNotPlaceholders() {
        for section in Jarvis.Section.allCases {
            let feature = feature("jarvis.\(section.rawValue)")
            #expect(feature.state("owner") == "AVAILABLE", "\(section.rawValue)")
            for plan in ["free", "basic", "vip"] { #expect(feature.state(plan) == "OWNER_ONLY", "\(section.rawValue) \(plan)") }
            #expect(section.isAvailable == (feature.placeholder == nil), "\(section.rawValue): ported state differs from the spec")
        }
        let owner = Profile(id: 1, role: "owner", subscription: nil)
        #expect(Jarvis.isAvailable(to: owner))
        for plan in ["free", "basic", "vip"] {
            #expect(!Jarvis.isAvailable(to: Profile(id: 2, role: "user", subscription: .init(plan: plan, status: "active"))))
        }
    }

    @Test func theOwnerCannotDeleteTheAccountFromTheApp() {
        #expect(feature("profile.delete").state("owner") == "HIDDEN_BY_SECURITY")
        #expect(!Profile(id: 1, role: "owner", subscription: nil).canDeleteAccountInApp)
        #expect(Profile(id: 2, role: "user", subscription: .init(plan: "vip", status: "active")).canDeleteAccountInApp)
    }
}
