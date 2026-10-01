import DincrCore
import DincrDesign
import SwiftUI
import UIKit

/// PARITY B1 — five sections; each owns its navigation stack. The app lock replaces the whole shell
/// while locked (sheets and alerts go with it), and global notices sit above every tab.
struct MainTabView: View {
    enum Tab: String, Hashable { case home, movements, plan, advisor, profile }

    @Environment(AppModel.self) private var model
    /// `-DincrTab <tab>` opens a given tab (screenshots and UI tests on fixture data).
    @State private var selection: Tab = {
        let args = ProcessInfo.processInfo.arguments
        guard let index = args.firstIndex(of: "-DincrTab"), args.indices.contains(index + 1) else { return .home }
        return Tab(rawValue: args[index + 1]) ?? .home
    }()
    @State private var profilePath = NavigationPath()
    @State private var offeringLock = false

    var body: some View {
        if model.appLock.locked {
            LockScreenView()
        } else {
            tabs
                .safeAreaInset(edge: .top, spacing: 0) { GlobalBanners() }
                .overlay(alignment: .bottom) { NoticeToast() }
                .onChange(of: selection, initial: true) { _, tab in model.trackScreen(tab.rawValue) }
                .onChange(of: model.pendingRoute) { _, route in
                    guard route == "mail" else { return }
                    model.pendingRoute = nil
                    selection = .profile
                    profilePath = NavigationPath([ProfileRoute.mail])
                }
                .task {
                    // A12 — one-time offer to turn the lock on after signing in.
                    if !model.environment.isFixtures, !model.appLock.wasOffered, model.appLock.availability != .unavailable {
                        offeringLock = true
                    }
                    if model.pendingRoute == "mail" {
                        model.pendingRoute = nil
                        selection = .profile
                        profilePath = NavigationPath([ProfileRoute.mail])
                    }
                }
                .alert(tx("¿Proteger DINCR con bloqueo?", "Protect DINCR with a lock?"), isPresented: $offeringLock) {
                    Button(tx("Activar", "Turn on")) { model.appLock.markOffered(); Task { _ = await model.appLock.setEnabled(true) } }
                    Button(tx("Ahora no", "Not now"), role: .cancel) { model.appLock.markOffered() }
                } message: {
                    Text(tx("Pedí tu Face ID, Touch ID o código al abrir DINCR y después de 5 minutos fuera.", "Ask for Face ID, Touch ID or your passcode when opening DINCR and after 5 minutes away."))
                }
        }
    }

    private var tabs: some View {
        // Classic tabItem API keeps the iOS 17 baseline.
        TabView(selection: $selection) {
            NavigationStack { HomeView(openMovements: { selection = .movements }) }
                .tabItem { Label(tx("Hoy", "Today"), systemImage: "chart.bar.xaxis") }
                .tag(Tab.home)
            NavigationStack { MovementsView() }
                .tabItem { Label(tx("Movimientos", "Transactions"), systemImage: "list.bullet.rectangle") }
                .tag(Tab.movements)
            NavigationStack { PlanHubView() }
                .tabItem { Label(tx("Plan", "Plan"), systemImage: "target") }
                .tag(Tab.plan)
            NavigationStack { AdvisorHubView() }
                .tabItem { Label("DINCR", systemImage: "sparkle") }
                .tag(Tab.advisor)
            NavigationStack(path: $profilePath) {
                ProfileHubView()
                    .navigationDestination(for: ProfileRoute.self) { route in
                        switch route {
                        case .mail: EmailMonitorView().onAppear { model.trackScreen("mail") }
                        case .jarvis: JarvisHubView().onAppear { model.trackJarvisOpened() }
                        case .jarvisSection(let section): JarvisSectionView(section: section).onAppear { model.trackJarvisSection(section) }
                        }
                    }
            }
            .tabItem { Label(tx("Perfil", "Profile"), systemImage: "person.crop.circle") }
            .tag(Tab.profile)
        }
    }
}

/// Routes of the Profile tab. JARVIS is the Owner's personal space (`Jarvis.isAvailable`).
enum ProfileRoute: Hashable {
    case mail
    case jarvis
    case jarvisSection(Jarvis.Section)
}

/// B5/B6/B7 and A1 — writes paused, subscription access notice, service health, optional update.
private struct GlobalBanners: View {
    @Environment(AppModel.self) private var model
    @State private var hiddenNotice: String?

    var body: some View {
        VStack(spacing: DincrSpacing.s2) {
            switch model.health?.status {
            case "degraded"?:
                StatusBanner(tone: .warning, title: tx("Servicio con demoras", "Service is slow"), message: tx("Algunas funciones pueden tardar más de lo normal.", "Some features may take longer than usual."))
            case "major_outage"?:
                StatusBanner(tone: .error, title: tx("Servicio interrumpido", "Service interrupted"), message: tx("Estamos trabajando para restablecer DINCR. Tus datos están a salvo.", "We’re working to restore DINCR. Your data is safe."))
            default:
                EmptyView()
            }
            if let notice = model.profile?.subscription?.accessNotice, let message = notice.message, hiddenNotice != notice.code {
                HStack(alignment: .top) {
                    StatusBanner(tone: .info, title: notice.title ?? tx("Tu plan", "Your plan"), message: message)
                    Button { hiddenNotice = notice.code } label: { Image(systemName: "xmark") }
                        .accessibilityLabel(tx("Cerrar aviso", "Dismiss notice"))
                        .frame(minWidth: 44, minHeight: 44)
                }
            }
            if let update = model.optionalUpdate {
                HStack(alignment: .top) {
                    StatusBanner(tone: .info, title: tx("Hay una versión nueva", "A new version is available"),
                                 message: update.message(model.language) ?? tx("Actualizá cuando puedas.", "Update when you can."))
                    Button { model.dismissOptionalUpdate() } label: { Image(systemName: "xmark") }
                        .accessibilityLabel(tx("Ahora no", "Not now"))
                        .frame(minWidth: 44, minHeight: 44)
                }
            }
        }
        .padding(.horizontal, DincrSpacing.s4)
        .frame(maxWidth: 640)
    }
}

/// A one-line app-wide confirmation (mail connected, plan saved…), dismissed after a few seconds.
private struct NoticeToast: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        if let notice = model.notice {
            Text(notice)
                .font(DincrFont.bodySmall.weight(.semibold))
                .foregroundStyle(DincrColor.onTint)
                .padding(.horizontal, DincrSpacing.s4).padding(.vertical, DincrSpacing.s3)
                .background(DincrColor.tint, in: Capsule())
                .padding(.bottom, 64)
                .accessibilityIdentifier("app.notice")
                .task(id: notice) {
                    UIAccessibility.post(notification: .announcement, argument: notice)
                    try? await Task.sleep(for: .seconds(4))
                    if model.notice == notice { model.notice = nil }
                }
        }
    }
}

/// A13 — the app is locked: unlock, or sign out.
private struct LockScreenView: View {
    @Environment(AppModel.self) private var model
    @State private var message: String?

    var body: some View {
        VStack(spacing: DincrSpacing.s4) {
            Spacer()
            Image(systemName: "lock.fill").font(.system(size: 40)).foregroundStyle(DincrColor.tint).accessibilityHidden(true)
            Text(tx("DINCR está bloqueado", "DINCR is locked")).font(DincrFont.title1)
            if let message, !message.isEmpty { Text(message).font(DincrFont.bodySmall).foregroundStyle(DincrColor.negative).multilineTextAlignment(.center) }
            Spacer()
            Button(tx("Desbloquear", "Unlock")) { Task { message = await model.appLock.unlock() } }.buttonStyle(.dincrPrimary)
            Button(tx("Cerrar sesión", "Sign out")) { Task { await model.signOut() } }.foregroundStyle(DincrColor.tint).frame(minHeight: 44)
        }
        .padding(DincrSpacing.s6)
        .frame(maxWidth: 600)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .dincrScreenBackground()
        .task { message = await model.appLock.unlock() }
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
