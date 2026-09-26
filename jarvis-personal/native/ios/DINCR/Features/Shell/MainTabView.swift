import DincrCore
import DincrDesign
import SwiftUI

/// PARITY B1 — five sections; each owns its navigation stack.
struct MainTabView: View {
    enum Tab: String, Hashable { case home, movements, plan, advisor, profile }
    /// `-DincrTab <tab>` opens a given tab (screenshots and store captures on fixture data).
    @State private var selection: Tab = {
        let args = ProcessInfo.processInfo.arguments
        guard let index = args.firstIndex(of: "-DincrTab"), args.indices.contains(index + 1) else { return .home }
        return Tab(rawValue: args[index + 1]) ?? .home
    }()

    var body: some View {
        // Classic tabItem API keeps the iOS 17 baseline. The iPad sidebar style
        // (`.sidebarAdaptable`) needs iOS 18 and waits for the baseline decision.
        TabView(selection: $selection) {
            NavigationStack { HomeView(openMovements: { selection = .movements }) }
                .tabItem { Label(tx("Hoy", "Today"), systemImage: "chart.bar.xaxis") }
                .tag(Tab.home)
            NavigationStack { MovementsView() }
                .tabItem { Label(tx("Movimientos", "Transactions"), systemImage: "list.bullet.rectangle") }
                .tag(Tab.movements)
            NavigationStack { PrototypePlaceholderView(title: tx("Plan", "Plan"), parity: "E1–E12") }
                .tabItem { Label(tx("Plan", "Plan"), systemImage: "target") }
                .tag(Tab.plan)
            NavigationStack { PrototypePlaceholderView(title: "DINCR", parity: "F1–F10") }
                .tabItem { Label("DINCR", systemImage: "sparkle") }
                .tag(Tab.advisor)
            NavigationStack { ProfileView() }
                .tabItem { Label(tx("Perfil", "Profile"), systemImage: "person.crop.circle") }
                .tag(Tab.profile)
        }
    }
}

/// Screens outside the prototype scope. Visible and honest, never a fake feature.
struct PrototypePlaceholderView: View {
    let title: String
    let parity: String

    var body: some View {
        ScrollView {
            EmptyStateView(
                symbol: "hammer",
                title: tx("En construcción", "Under construction"),
                message: tx("Esta sección llega en los módulos siguientes de la app nativa (\(parity)). Mientras tanto, usala desde la app actual de DINCR.", "This section arrives in the next native modules (\(parity)). Meanwhile, use it in the current DINCR app.")
            ) { EmptyView() }
            .padding(DincrSpacing.s4)
        }
        .dincrScreenBackground()
        .navigationTitle(title)
    }
}

struct ProfileView: View {
    @Environment(AppModel.self) private var model
    @AppStorage("dincr.appearance") private var appearance = Appearance.system.rawValue
    @State private var confirmingSignOut = false

    var body: some View {
        List {
            Section {
                HStack(spacing: DincrSpacing.s3) {
                    Text(String(model.profile?.firstName?.prefix(1) ?? "D"))
                        .font(DincrFont.title2).foregroundStyle(DincrColor.onTintContainer)
                        .frame(width: 44, height: 44).background(DincrColor.tintContainer, in: Circle())
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(model.profile?.displayName ?? tx("Tu cuenta", "Your account")).font(DincrFont.title2)
                        Text(model.profile?.email ?? "").font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                    }
                    Spacer()
                    PlanBadge(plan: model.profile?.plan ?? "free")
                }
                .accessibilityElement(children: .combine)
            }
            Section(tx("Apariencia", "Appearance")) {
                Picker(tx("Tema", "Theme"), selection: $appearance) {
                    Text(tx("Automático", "Automatic")).tag(Appearance.system.rawValue)
                    Text(tx("Claro", "Light")).tag(Appearance.light.rawValue)
                    Text(tx("Oscuro", "Dark")).tag(Appearance.dark.rawValue)
                }
            }
            Section {
                Button(tx("Cerrar sesión", "Sign out"), role: .destructive) { confirmingSignOut = true }
            }
        }
        .scrollContentBackground(.hidden)
        .dincrScreenBackground()
        .navigationTitle(tx("Perfil", "Profile"))
        .confirmationDialog(tx("¿Cerrar sesión en este dispositivo?", "Sign out on this device?"), isPresented: $confirmingSignOut, titleVisibility: .visible) {
            Button(tx("Cerrar sesión", "Sign out"), role: .destructive) { Task { await model.signOut() } }
            Button(tx("Cancelar", "Cancel"), role: .cancel) {}
        }
    }
}

/// Display name of a backend plan code. The plan itself always comes from `/auth/me`.
enum PlanLabel {
    static func name(_ plan: String?) -> String {
        switch plan ?? "free" {
        case "free": tx("Gratis", "Free")
        case "vip": "VIP"
        case let other: other.capitalized
        }
    }
}

/// Quiet plan badge; VIP uses its reserved color (DESIGN.md → plan-badge-vip).
struct PlanBadge: View {
    let plan: String
    var body: some View {
        let vip = plan == "vip"
        Text(PlanLabel.name(plan))
            .font(DincrFont.caption.weight(.semibold))
            .foregroundStyle(vip ? DincrColor.vip : DincrColor.text2)
            .padding(.horizontal, 8).padding(.vertical, 2)
            .background(vip ? DincrColor.vipContainer : DincrColor.surface2, in: Capsule())
            .accessibilityLabel(tx("Plan \(PlanLabel.name(plan))", "\(PlanLabel.name(plan)) plan"))
    }
}
