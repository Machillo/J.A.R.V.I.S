import DincrCore
import DincrDesign
import SwiftUI

@main
struct DINCRApp: App {
    @State private var model = AppModel()
    @AppStorage("dincr.appearance") private var appearance = Appearance.system.rawValue
    @Environment(\.scenePhase) private var scenePhase
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
                .task {
                    DataExport.clear()
                    await model.start()
                }
                // A mail OAuth return opened by the system (the authentication session delivers it
                // directly otherwise). Sign-in callbacks only ever come through the session.
                .onOpenURL { url in Task { await model.handleOpenURL(url) } }
                // The app-switcher snapshot is taken while inactive: with the lock on, it shows a cover,
                // never balances.
                .overlay {
                    if scenePhase != .active && model.appLock.isEnabled {
                        ZStack {
                            DincrColor.bg.ignoresSafeArea()
                            Image(systemName: "lock.fill").font(.system(size: 40)).foregroundStyle(DincrColor.tint)
                        }
                        .accessibilityHidden(true)
                    }
                }
                .onChange(of: scenePhase) { _, phase in
                    switch phase {
                    case .active: Task { await model.onForeground() }
                    case .background: model.onBackground()
                    default: break
                    }
                }
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

/// Short bilingual copy helper, same contract as the web `tx(es, en)`: Spanish (Costa Rica,
/// voseo) or English, from the device language (the Capacitor app has no in-app language setting).
func tx(_ spanish: String, _ english: String) -> String { AppLanguage.current.pick(spanish, english) }
