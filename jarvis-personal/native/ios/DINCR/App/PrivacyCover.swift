import DincrDesign
import SwiftUI
import UIKit

/// M4 — hides the app while it is not active (app switcher, Control Center, notification pull-down)
/// when the app lock is on. It is a separate window at a level above alerts, so it also covers sheets,
/// confirmation dialogs and the share sheet that a SwiftUI overlay on the root view cannot reach.
@MainActor
final class PrivacyCover {
    static let shared = PrivacyCover()
    private var window: UIWindow?

    func update(visible: Bool) {
        if visible { show() } else { hide() }
    }

    private func show() {
        guard window == nil,
              let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first else { return }
        let cover = UIWindow(windowScene: scene)
        cover.windowLevel = .alert + 1
        let controller = UIHostingController(rootView: CoverView())
        controller.view.backgroundColor = .clear
        cover.rootViewController = controller
        cover.isHidden = false
        window = cover
    }

    private func hide() {
        window?.isHidden = true
        window = nil
    }

    private struct CoverView: View {
        var body: some View {
            ZStack {
                DincrColor.bg.ignoresSafeArea()
                Image(systemName: "lock.fill").font(.system(size: 40)).foregroundStyle(DincrColor.tint)
            }
            .accessibilityHidden(true)
        }
    }
}
