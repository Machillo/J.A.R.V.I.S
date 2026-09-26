import DincrCore
import DincrDesign
import SwiftUI

struct RootView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        Group {
            switch model.phase {
            case .booting, .loadingIdentity:
                BootView()
            case .signedOut:
                LoginView()
            case .identityError(let message):
                GateMessageView(
                    symbol: "exclamationmark.triangle",
                    title: tx("No pudimos cargar tu cuenta", "We couldn’t load your account"),
                    message: message,
                    primary: (tx("Intentar de nuevo", "Try again"), { Task { await model.loadIdentity() } })
                )
            case .ownerNotSupported:
                // Owner boundary (CLAUDE.md §4.A): the public app never renders Owner features.
                GateMessageView(
                    symbol: "lock.shield",
                    title: tx("Esta cuenta usa DINCR Owner", "This account uses DINCR Owner"),
                    message: tx("La app pública de DINCR no muestra funciones internas. Cerrá sesión para entrar con otra cuenta.", "The public DINCR app doesn’t show internal features. Sign out to use another account."),
                    primary: nil
                )
            case .notYetSupported(let message):
                GateMessageView(symbol: "hourglass", title: tx("Un paso más", "One more step"), message: message, primary: nil)
            case .profileSetup:
                ProfileSetupView()
            case .ready:
                MainTabView()
            }
        }
        .animation(DincrMotion.standard(reduceMotion), value: model.phase)
    }
}

private struct BootView: View {
    var body: some View {
        VStack(spacing: DincrSpacing.s3) {
            BrandMark(size: 56)
            ProgressView().tint(DincrColor.tint)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .dincrScreenBackground()
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(tx("Preparando tu espacio", "Preparing your space"))
    }
}

/// Full-screen gate with the recovery next to the problem and a way out (sign out).
struct GateMessageView: View {
    @Environment(AppModel.self) private var model
    let symbol: String
    let title: String
    let message: String
    let primary: (String, () -> Void)?

    var body: some View {
        VStack(spacing: DincrSpacing.s4) {
            Spacer()
            Image(systemName: symbol).font(.system(size: 40)).foregroundStyle(DincrColor.tint).accessibilityHidden(true)
            Text(title).font(DincrFont.title1).foregroundStyle(DincrColor.text).multilineTextAlignment(.center)
            Text(message).font(DincrFont.body).foregroundStyle(DincrColor.text2).multilineTextAlignment(.center)
            Spacer()
            if let primary {
                Button(primary.0, action: primary.1).buttonStyle(.dincrPrimary)
            }
            Button(tx("Cerrar sesión", "Sign out")) { Task { await model.signOut() } }
                .font(DincrFont.title2)
                .foregroundStyle(DincrColor.tint)
                .frame(minHeight: 44)
        }
        .padding(DincrSpacing.s6)
        .frame(maxWidth: 600)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .dincrScreenBackground()
    }
}

/// The "D" monogram (no vector master exists yet — PRODUCT.md open item).
struct BrandMark: View {
    var size: CGFloat = 48
    var body: some View {
        Text("D")
            .font(.system(size: size * 0.55, weight: .heavy, design: .rounded))
            .foregroundStyle(DincrColor.onTint)
            .frame(width: size, height: size)
            .background(DincrColor.tint, in: RoundedRectangle(cornerRadius: size * 0.28, style: .continuous))
            .accessibilityHidden(true)
    }
}
