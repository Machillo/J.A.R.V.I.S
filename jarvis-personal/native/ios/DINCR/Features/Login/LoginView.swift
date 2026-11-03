import AuthenticationServices
import DincrCore
import DincrDesign
import SwiftUI

/// PARITY A2 (Google), A3 (Apple, iOS only). OAuth runs in the system authentication session
/// with PKCE; only the returned code is accepted.
struct LoginView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.webAuthenticationSession) private var webAuthenticationSession
    @State private var activeProvider: OAuthProvider?

    /// The opening: the brand alone on the dark scene, then the scene settles and the sign-in appears.
    @State private var opening = true
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dincrDecorativeMotion) private var decorativeMotion

    private var animates: Bool { !reduceMotion && decorativeMotion }

    var body: some View {
        GeometryReader { geometry in
            let fullHeight = geometry.size.height + geometry.safeAreaInsets.top + geometry.safeAreaInsets.bottom
            let settled = min(max(fullHeight * 0.36, 240), 340)
            ZStack(alignment: .top) {
                OwnerColor.surface.ignoresSafeArea()
                scene(height: opening ? fullHeight + 120 : settled)
                ScrollView {
                    signIn
                        .padding(.top, settled - geometry.safeAreaInsets.top + DincrSpacing.s2)
                        .opacity(opening ? 0 : 1)
                        .offset(y: opening ? 24 : 0)
                }
                .scrollBounceBehavior(.basedOnSize)
                wordmark(top: geometry.safeAreaInsets.top, centered: opening, fullHeight: fullHeight)
            }
        }
        .task {
            guard animates else { opening = false; return }
            try? await Task.sleep(for: .milliseconds(850))
            withAnimation(.spring(duration: 0.75, bounce: 0.12)) { opening = false }
        }
    }

    /// The dark scene with its curved edge. Decorative.
    private func scene(height: CGFloat) -> some View {
        LoginCurve()
            .fill(LinearGradient(colors: [Color.black, Color(red: 0.043, green: 0.086, blue: 0.149)], startPoint: .top, endPoint: .bottom))
            .frame(height: height)
            .ignoresSafeArea(edges: .top)
            .accessibilityHidden(true)
    }

    private func wordmark(top: CGFloat, centered: Bool, fullHeight: CGFloat) -> some View {
        VStack(alignment: centered ? .center : .leading, spacing: DincrSpacing.s2) {
            Text("DINCR")
                .font(.system(size: centered ? 40 : 22, weight: .semibold))
                .tracking(centered ? 10 : 6)
                .foregroundStyle(.white)
                .accessibilityAddTraits(.isHeader)
            Text(tx("Tu dinero, con propósito", "Your money, with purpose"))
                .font(DincrFont.bodySmall)
                .foregroundStyle(.white.opacity(0.72))
        }
        .frame(maxWidth: .infinity, alignment: centered ? .center : .leading)
        .padding(.horizontal, DincrSpacing.s6)
        .padding(.top, centered ? fullHeight * 0.42 - top : DincrSpacing.s6)
        .allowsHitTesting(false)
    }

    private var signIn: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s5) {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                Text(tx("Entrá a tu cuenta", "Sign in to your account"))
                    .font(.title.weight(.bold))
                    .foregroundStyle(OwnerColor.text)
                    .accessibilityAddTraits(.isHeader)
                Text(tx("Ordená tus ingresos, gastos, deudas y metas, y sabé qué sigue.", "Organize your income, expenses, debts and goals, and know what comes next."))
                    .font(DincrFont.body)
                    .foregroundStyle(OwnerColor.text2)
            }

            VStack(spacing: DincrSpacing.s3) {
                signInButton(.google, title: tx("Continuar con Google", "Continue with Google"))
                signInButton(.apple, title: tx("Continuar con Apple", "Continue with Apple"))
            }

            if let error = model.signInError {
                ErrorStateView(message: error)
                    .accessibilitySortPriority(1)
            }

            Label {
                Text(tx("Se abrirá una ventana segura para iniciar sesión. DINCR nunca ve tu contraseña.", "A secure window will open to sign in. DINCR never sees your password."))
            } icon: {
                Image(systemName: "lock.shield")
            }
            .font(DincrFont.bodySmall)
            .foregroundStyle(OwnerColor.textMuted)

            if model.environment.isFixtures {
                StatusBanner(tone: .info, title: tx("Modo de demostración", "Demo mode"), message: tx("Datos de ejemplo. No se conecta a ninguna cuenta real.", "Sample data. Not connected to any real account."))
            }
        }
        .padding(.horizontal, DincrSpacing.s6)
        .padding(.bottom, DincrSpacing.s6)
        .frame(maxWidth: 600)
        .frame(maxWidth: .infinity)
    }

    /// Provider buttons follow each provider's branding rules: Google's light button with the
    /// official "G", Apple's black/white button with the Apple logo.
    private func signInButton(_ provider: OAuthProvider, title: String) -> some View {
        Button {
            Task { await signIn(provider) }
        } label: {
            HStack(spacing: DincrSpacing.s3) {
                if activeProvider == provider {
                    ProgressView()
                } else if provider == .google {
                    Image("GoogleG").resizable().frame(width: 20, height: 20).accessibilityHidden(true)
                } else {
                    Image(systemName: "apple.logo").font(.system(size: 19, weight: .medium)).accessibilityHidden(true)
                }
                Text(title).font(DincrFont.body.weight(.semibold))
            }
            .frame(maxWidth: .infinity, minHeight: 52)
        }
        .buttonStyle(ProviderButtonStyle(provider: provider))
        .disabled(activeProvider != nil || model.isSigningIn)
        .accessibilityIdentifier("login.\(provider.rawValue)")
    }

    private func signIn(_ provider: OAuthProvider) async {
        activeProvider = provider
        defer { activeProvider = nil }
        if model.environment.isFixtures {
            await model.signInWithFixtures()
            return
        }
        guard let url = model.beginSignIn(provider: provider) else { return }
        do {
            let callback = try await webAuthenticationSession.authenticate(
                using: url, callbackURLScheme: AppEnvironment.authCallbackScheme, preferredBrowserSession: .ephemeral)
            await model.completeSignIn(callback: callback)
        } catch let error as ASWebAuthenticationSessionError where error.code == .canceledLogin {
            model.signInCancelled()
        } catch {
            model.signInCancelled()
            model.signInError = tx("No pudimos completar el acceso. Intentá nuevamente.", "We couldn’t sign you in. Please try again.")
        }
    }
}

/// The dark scene's edge: straight on top, one soft curve below.
private struct LoginCurve: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let edge = rect.height * 0.82
        path.move(to: .zero)
        path.addLine(to: CGPoint(x: rect.width, y: 0))
        path.addLine(to: CGPoint(x: rect.width, y: edge * 0.82))
        path.addQuadCurve(to: CGPoint(x: 0, y: edge), control: CGPoint(x: rect.width * 0.45, y: rect.height * 1.12))
        path.closeSubpath()
        return path
    }
}

private struct ProviderButtonStyle: ButtonStyle {
    let provider: OAuthProvider
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        let dark = colorScheme == .dark
        let (fill, text, border): (Color, Color, Color) = switch provider {
        // Google light theme: #FFFFFF fill, #1F1F1F text, #747775 stroke.
        case .google: (.white, Color(red: 0.12, green: 0.12, blue: 0.12), Color(red: 0.455, green: 0.467, blue: 0.459))
        // Apple: black on light backgrounds, white on dark.
        case .apple: (dark ? .white : .black, dark ? .black : .white, .clear)
        }
        return configuration.label
            .foregroundStyle(text)
            .tint(text)
            .background(fill, in: RoundedRectangle(cornerRadius: DincrRadius.md, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: DincrRadius.md, style: .continuous).strokeBorder(border, lineWidth: 1))
            .opacity(isEnabled ? (configuration.isPressed ? 0.85 : 1) : 0.5)
            .contentShape(Rectangle())
    }
}
