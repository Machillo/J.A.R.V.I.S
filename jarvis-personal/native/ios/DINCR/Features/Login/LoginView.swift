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

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DincrSpacing.s6) {
                HStack(spacing: DincrSpacing.s3) {
                    BrandMark(size: 44)
                    Text("DINCR").font(DincrFont.title2).tracking(2).foregroundStyle(DincrColor.text)
                }
                .padding(.top, DincrSpacing.s8)

                VStack(alignment: .leading, spacing: DincrSpacing.s3) {
                    Text(tx("Tu dinero, con propósito", "Your money, with purpose"))
                        .font(.largeTitle.weight(.bold))
                        .foregroundStyle(DincrColor.text)
                        .accessibilityAddTraits(.isHeader)
                    Text(tx("Ordená tus ingresos, gastos, deudas y metas, y sabé qué sigue.", "Organize your income, expenses, debts and goals, and know what comes next."))
                        .font(DincrFont.body)
                        .foregroundStyle(DincrColor.text2)
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
                .foregroundStyle(DincrColor.textMuted)

                if model.environment.isFixtures {
                    StatusBanner(tone: .info, title: tx("Modo de demostración", "Demo mode"), message: tx("Datos de ejemplo. No se conecta a ninguna cuenta real.", "Sample data. Not connected to any real account."))
                }
            }
            .padding(.horizontal, DincrSpacing.s4)
            .frame(maxWidth: 600)
            .frame(maxWidth: .infinity)
        }
        .dincrScreenBackground()
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
                Text(title).font(DincrFont.title2)
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
