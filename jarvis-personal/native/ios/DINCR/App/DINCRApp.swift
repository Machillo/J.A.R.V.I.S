import DincrCore
import DincrDesign
import SwiftUI

@main
struct DINCRApp: App {
    @State private var model = AppModel()
    @AppStorage("dincr.appearance") private var appearance = Appearance.system.rawValue
    /// UI tests pass `-DincrDisableAnimations` so the app can go idle (looping animations block XCUITest).
    private let animationsDisabled = ProcessInfo.processInfo.arguments.contains("-DincrDisableAnimations")

    init() {
        if animationsDisabled { UIView.setAnimationsEnabled(false) }
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
                .environment(\.moneyFormat, model.moneyFormat)
                .environment(\.dincrDecorativeMotion, !animationsDisabled)
                .preferredColorScheme(Appearance(rawValue: appearance)?.colorScheme)
                .tint(DincrColor.tint)
                .task { await model.start() }
        }
    }
}

/// In-app appearance override (DESIGN.md: follow the system by default).
enum Appearance: String, CaseIterable, Identifiable {
    case system, light, dark
    var id: String { rawValue }
    var colorScheme: ColorScheme? {
        switch self {
        case .system: nil
        case .light: .light
        case .dark: .dark
        }
    }
}

/// Short bilingual copy helper, same contract as the web `tx(es, en)`.
/// Prototype only: module work moves strings to a String Catalog.
func tx(_ spanish: String, _ english: String) -> String { AppLanguage.current.pick(spanish, english) }
