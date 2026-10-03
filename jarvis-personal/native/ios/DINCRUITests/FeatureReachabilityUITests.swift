import XCTest

/// Functional protection gate (master plan R1 / P0.0): every feature in the shared reachability spec
/// (`native/feature-reachability.json`) is reachable, locked or absent for each plan exactly as the
/// spec says, on the fixture backend. A PR that removes, hides or moves a feature fails here unless it
/// changes the spec with an explicit decision. Android walks the same spec in `FeatureReachabilityUiTest`.
@MainActor
final class FeatureReachabilityUITests: XCTestCase {
    struct Spec: Decodable {
        struct Location: Decodable {
            let tab: String?
            let tabButton: String?
            let via: [String]?
            let id: String?
            let ownerId: String?
            let label: String?
            let lockedLabel: String?

            enum CodingKeys: String, CodingKey {
                case tab, via, id, label, tabButton = "tab_button", ownerId = "owner_id", lockedLabel = "locked_label"
            }
        }
        struct Feature: Decodable {
            let id: String
            let plans: [String: String]
            let platformStates: [String: [String: String]]?
            let ios: Location?

            enum CodingKeys: String, CodingKey { case id, plans, ios, platformStates = "platform_states" }

            func state(_ plan: String) -> String { platformStates?["ios"]?[plan] ?? plans[plan] ?? "" }
        }
        let features: [Feature]
    }

    static let spec: Spec = {
        // native/ios/DINCRUITests/<this file> → native/feature-reachability.json
        var url = URL(fileURLWithPath: #filePath)
        for _ in 0..<3 { url.deleteLastPathComponent() }
        let data = try! Data(contentsOf: url.appendingPathComponent("feature-reachability.json"))
        return try! JSONDecoder().decode(Spec.self, from: data)
    }()

    private func launch(plan: String, tab: String) -> XCUIApplication {
        let app = XCUIApplication()
        var arguments = ["-DincrDisableAnimations", "-DincrFixtures", "populated", "-DincrSkipLogin", "-DincrTab", tab,
                         "-AppleLanguages", "(es)", "-AppleLocale", "es_CR"]
        switch plan {
        case "owner": arguments += ["-DincrRole", "owner"]
        case "free": break
        default: arguments += ["-DincrPlan", plan]
        }
        app.launchArguments = arguments
        app.launch()
        return app
    }

    private func element(_ location: Spec.Location, plan: String, in app: XCUIApplication) -> XCUIElement {
        if let identifier = (plan == "owner" ? location.ownerId : nil) ?? location.id {
            return app.descendants(matching: .any)[identifier].firstMatch
        }
        return app.descendants(matching: .any).matching(NSPredicate(format: "label == %@", location.label ?? "")).firstMatch
    }

    /// One sweep of the current screen: every target is looked up at the top and after each of up to six
    /// swipes; returns, per feature id, whether it appeared and its accessibility label when it did.
    private func survey(_ targets: [(String, XCUIElement)], in app: XCUIApplication) -> [String: String?] {
        _ = app.tabBars.firstMatch.waitForExistence(timeout: 10)
        var seen: [String: String?] = [:]
        func look() {
            for (id, target) in targets where seen[id] == nil && target.exists { seen[id] = .some(target.label) }
        }
        _ = targets.first?.1.waitForExistence(timeout: 3)
        look()
        for _ in 0..<6 where seen.count < targets.count {
            app.swipeUp()
            look()
        }
        return seen
    }

    private func check(_ feature: Spec.Feature, plan: String, seen: [String: String?], in app: XCUIApplication) {
        guard let location = feature.ios else { return }
        let state = feature.state(plan)
        let context = "\(feature.id) [\(plan)] expected \(state)"
        if let tab = location.tabButton {
            XCTAssertEqual(app.tabBars.buttons[tab].exists, state == "AVAILABLE", context)
            return
        }
        let label = seen[feature.id] ?? nil
        let shown = seen[feature.id] != nil
        switch state {
        case "AVAILABLE":
            XCTAssertTrue(shown, "\(context): not reachable")
            if let locked = location.lockedLabel, let label { XCTAssertFalse(label.contains(locked), "\(context): shown locked") }
        case "VISIBLE_LOCKED":
            XCTAssertTrue(shown, "\(context): the locked entry is missing")
            if let locked = location.lockedLabel { XCTAssertTrue(label?.contains(locked) == true, "\(context): not shown locked (\(label ?? "-"))") }
        default:  // OWNER_ONLY, HIDDEN_BY_SECURITY, HIDDEN_BY_PLAN: never shown to this plan
            XCTAssertFalse(shown, "\(context): shown to a plan that must not see it")
        }
    }

    /// One launch per plan and screen: the screen's entries are checked together.
    private func walk(plan: String) {
        continueAfterFailure = true
        let located = Self.spec.features.filter { $0.ios != nil }
        let groups = Dictionary(grouping: located) { feature -> String in
            let location = feature.ios!
            return (location.tabButton != nil ? "home" : location.tab ?? "home") + "|" + (location.via ?? []).joined(separator: ">")
        }
        for key in groups.keys.sorted() {
            let parts = key.split(separator: "|", omittingEmptySubsequences: false)
            let app = launch(plan: plan, tab: String(parts[0]))
            var reached = true
            for step in parts[1].split(separator: ">").map(String.init) {
                let entry = app.descendants(matching: .any)[step].firstMatch
                guard survey([(step, entry)], in: app)[step] != nil else { reached = false; break }
                entry.tap()
            }
            let features = groups[key]!
            let targets = features.filter { $0.ios?.tabButton == nil }.map { ($0.id, element($0.ios!, plan: plan, in: app)) }
            let seen = reached ? survey(targets, in: app) : [:]
            for feature in features {
                if reached {
                    check(feature, plan: plan, seen: seen, in: app)
                } else {
                    // The path itself is closed for this plan: the feature must be one this plan never sees.
                    XCTAssertFalse(["AVAILABLE", "VISIBLE_LOCKED"].contains(feature.state(plan)),
                                   "\(feature.id) [\(plan)]: its path \(parts[1]) is not reachable")
                }
            }
            app.terminate()
        }
    }

    func testFreeReachesExactlyTheSpec() { walk(plan: "free") }
    func testBasicReachesExactlyTheSpec() { walk(plan: "basic") }
    func testVipReachesExactlyTheSpec() { walk(plan: "vip") }
    func testOwnerReachesExactlyTheSpec() { walk(plan: "owner") }
}
