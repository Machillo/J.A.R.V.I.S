import DincrCore
import Foundation
import Observation

/// Session and identity state. Reproduces the Capacitor gate order (CURRENT_STATE_AUDIT.md §1):
/// session → identity → Owner boundary → legal → profile setup → plan → app.
@MainActor @Observable
final class AppModel {
    enum Phase: Equatable {
        case booting
        case signedOut
        case loadingIdentity
        case identityError(String)
        case ownerNotSupported
        /// Legal consent and plan selection exist in the Capacitor app; the prototype routes
        /// those accounts to a notice until the modules land (PARITY_MATRIX A8, A11).
        case notYetSupported(String)
        case profileSetup
        case ready
    }

    private(set) var phase: Phase = .booting
    private(set) var profile: Profile?
    var signInError: String?
    private(set) var isSigningIn = false

    let service: DincrService
    let environment: AppEnvironment
    private let sessions: SessionManager
    private let auth: SupabaseAuthClient?
    private var pendingPKCE: PKCE?

    init(environment: AppEnvironment = .current()) {
        self.environment = environment
        switch environment.mode {
        case let .live(apiURL, supabaseURL, anonKey):
            let auth = SupabaseAuthClient(projectURL: supabaseURL, anonKey: anonKey)
            let sessions = SessionManager(auth: auth, store: KeychainSessionStore())
            self.auth = auth
            self.sessions = sessions
            self.service = LiveDincrService(client: APIClient(baseURL: apiURL, tokens: sessions))
        case let .fixtures(scenario):
            self.auth = nil
            self.sessions = SessionManager(auth: nil, store: InMemorySessionStore())
            self.service = FixtureDincrService(scenario: scenario)
        }
    }

    var language: AppLanguage { .current }
    var moneyFormat: MoneyFormat { MoneyFormat(profile: profile) }

    func start() async {
        await sessions.setSignedOutHandler { [weak self] in
            Task { @MainActor in self?.handleSignedOut() }
        }
        if environment.isFixtures {
            // Fixture sessions start signed out so the login screen is part of every flow.
            phase = ProcessInfo.processInfo.arguments.contains("-DincrSkipLogin") ? .loadingIdentity : .signedOut
            if phase == .loadingIdentity { await loadIdentity() }
            return
        }
        if await sessions.hasSession {
            await loadIdentity()
        } else {
            phase = .signedOut
        }
    }

    // MARK: Sign in

    /// The URL to open in the system authentication session.
    func beginSignIn(provider: OAuthProvider) -> URL? {
        signInError = nil
        guard let auth else { return nil }
        let pkce = PKCE.generate()
        pendingPKCE = pkce
        return auth.authorizeURL(provider: provider, redirectTo: AppEnvironment.authRedirect, pkce: pkce)
    }

    func completeSignIn(callback: URL) async {
        guard let auth, let pkce = pendingPKCE else { return }
        pendingPKCE = nil
        isSigningIn = true
        defer { isSigningIn = false }
        do {
            let code = try SupabaseAuthClient.authorizationCode(from: callback, redirect: AppEnvironment.authRedirect)
            let session = try await auth.exchange(code: code, verifier: pkce.verifier)
            await sessions.accept(session)
            await loadIdentity()
        } catch {
            signInError = language.pick("No pudimos completar el acceso. Intentá nuevamente.", "We couldn’t sign you in. Please try again.")
        }
    }

    func signInCancelled() {
        pendingPKCE = nil
    }

    /// Fixture mode: skip the provider and continue as the synthetic account.
    func signInWithFixtures() async {
        isSigningIn = true
        defer { isSigningIn = false }
        await loadIdentity()
    }

    // MARK: Identity

    func loadIdentity() async {
        if profile == nil { phase = .loadingIdentity }
        do {
            apply(try await service.me())
        } catch AuthError.signedOut {
            handleSignedOut()
        } catch let error as APIError {
            phase = .identityError(error.message)
        } catch {
            phase = .identityError(language.pick("No pudimos cargar tu cuenta.", "We couldn’t load your account."))
        }
    }

    func apply(_ profile: Profile) {
        self.profile = profile
        if profile.isOwner {
            phase = .ownerNotSupported
        } else if profile.legal?.required == true {
            phase = .notYetSupported(language.pick("Aceptá los términos actualizados desde la app actual de DINCR.", "Accept the updated terms in the current DINCR app."))
        } else if profile.profileSetupCompleted != true {
            phase = .profileSetup
        } else if profile.planSelected != true {
            phase = .notYetSupported(language.pick("Elegí tu plan desde la app actual de DINCR.", "Choose your plan in the current DINCR app."))
        } else {
            phase = .ready
        }
    }

    func signOut() async {
        await sessions.signOut()
        handleSignedOut()
    }

    private func handleSignedOut() {
        profile = nil
        phase = .signedOut
    }
}
