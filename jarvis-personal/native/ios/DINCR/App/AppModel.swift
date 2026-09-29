import DincrCore
import Foundation
import Observation

/// Session and identity state. Reproduces the Capacitor gate order (CURRENT_STATE_AUDIT.md §1):
/// session → identity → Owner boundary → legal → profile setup → plan → app.
@MainActor @Observable
final class AppModel {
    enum Phase: Equatable {
        case booting
        /// No usable backend configuration: nothing loads, and no sample data stands in for it.
        case unconfigured(LaunchPolicy.Reason)
        case signedOut
        case loadingIdentity
        case identityError(String)
        case ownerNotSupported
        /// A8 — updated terms or privacy policy must be accepted before anything else.
        case legalRequired
        /// A11 — first plan choice.
        case choosePlan
        case profileSetup
        case ready
    }

    private(set) var phase: Phase = .booting
    private(set) var profile: Profile?
    var signInError: String?
    private(set) var isSigningIn = false
    /// B5 — operational kill switches; unknown until loaded, which means each flag's safe default.
    private(set) var flags: FeatureFlags = .unknown
    var planTier: PlanTier { profile?.planTier ?? .free }

    let service: DincrService
    let environment: AppEnvironment
    private let sessions: SessionManager
    private let auth: SupabaseAuthClient?
    private var pendingPKCE: PKCE?
    /// Changes on every sign-in and sign-out. An identity answer that arrives after the session it
    /// was asked for is gone belongs to nobody: it never shows one account's name, formats or
    /// gates to the next account (or after signing out).
    private var sessionEpoch = 0
    /// Screens capture this before a call and pass it to `message(for:epoch:fallback:)`.
    var currentEpoch: Int { sessionEpoch }

    init(environment: AppEnvironment = .current()) {
        self.environment = environment
        switch environment.mode {
        case let .live(apiURL, supabaseURL, anonKey):
            let auth = SupabaseAuthClient(projectURL: supabaseURL, anonKey: anonKey)
            let sessions = SessionManager(auth: auth, store: KeychainSessionStore())
            self.auth = auth
            self.sessions = sessions
            self.service = LiveDincrService(client: APIClient(baseURL: apiURL, tokens: sessions))
        case let .fixtures(scenario, plan):
            self.auth = nil
            self.sessions = SessionManager(auth: nil, store: InMemorySessionStore())
            self.service = FixtureDincrService(scenario: scenario, plan: plan)
        case let .unconfigured(reason):
            self.auth = nil
            self.sessions = SessionManager(auth: nil, store: InMemorySessionStore())
            self.service = UnconfiguredService()
            self.phase = .unconfigured(reason)
        }
    }

    var language: AppLanguage { .current }
    var moneyFormat: MoneyFormat { MoneyFormat(profile: profile) }

    func start() async {
        if case .unconfigured = environment.mode { return }
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
            sessionEpoch += 1
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
        let epoch = sessionEpoch
        if profile == nil { phase = .loadingIdentity }
        do {
            let loaded = try await service.me()
            if epoch == sessionEpoch { apply(loaded) }
        } catch AuthError.signedOut {
            if epoch == sessionEpoch { handleSignedOut() }
        } catch AuthError.sessionChanged {
            // The session was replaced or closed while loading; its phase is already set.
        } catch let error as APIError {
            if epoch == sessionEpoch { phase = .identityError(error.message) }
        } catch {
            if epoch == sessionEpoch { phase = .identityError(language.pick("No pudimos cargar tu cuenta.", "We couldn’t load your account.")) }
        }
    }

    func apply(_ profile: Profile) {
        self.profile = profile
        if profile.isOwner {
            phase = .ownerNotSupported
        } else if profile.legal?.required == true {
            phase = .legalRequired
        } else if profile.profileSetupCompleted != true {
            phase = .profileSetup
        } else if profile.planSelected != true {
            phase = .choosePlan
        } else {
            phase = .ready
            Task { await refreshFlags() }
        }
    }

    // MARK: Gates

    /// Accepts exactly the versions `/auth/me` asked for, then reloads the identity. Returns an
    /// error message to show, or nil.
    func acceptLegal() async -> String? {
        guard let legal = profile?.legal, let terms = legal.termsVersion, let privacy = legal.privacyVersion else {
            return language.pick("No pudimos leer la versión de los términos. Intentá de nuevo.", "We couldn’t read the terms version. Please try again.")
        }
        let epoch = sessionEpoch
        do {
            _ = try await service.acceptLegal(LegalAcceptRequest(termsVersion: terms, privacyVersion: privacy))
            if epoch == sessionEpoch { await loadIdentity() }
            return nil
        } catch {
            return message(for: error, epoch: epoch, fallback: language.pick("No pudimos guardar tu aceptación.", "We couldn’t save your acceptance."))
        }
    }

    func choosePlan(_ code: String) async -> String? {
        let epoch = sessionEpoch
        do {
            let result = try await service.choosePlan(PlanChangeRequest(plan: code))
            guard epoch == sessionEpoch else { return nil }
            if let updated = result.profile { apply(updated) } else { await loadIdentity() }
            return nil
        } catch {
            return message(for: error, epoch: epoch, fallback: language.pick("No pudimos guardar tu plan.", "We couldn’t save your plan."))
        }
    }

    func refreshFlags() async {
        let epoch = sessionEpoch
        // A failed load keeps the last known flags (or the safe defaults); it never enables anything.
        if let loaded = try? await service.featureFlags(), epoch == sessionEpoch { flags = loaded }
    }

    /// G8 — the backend schedules the deletion; this device then forgets the session.
    func deleteAccount() async -> String? {
        let epoch = sessionEpoch
        do {
            try await service.deleteAccount()
            if epoch == sessionEpoch { await signOut() }
            return nil
        } catch {
            return message(for: error, epoch: epoch, fallback: language.pick("No pudimos eliminar tu cuenta.", "We couldn’t delete your account."))
        }
    }

    /// The message for a failed call, or nil when the session ended meanwhile (the gate already
    /// changed, so nothing is shown on a screen that belongs to nobody).
    func message(for error: Error, epoch: Int, fallback: String) -> String? {
        if epoch != sessionEpoch { return nil }
        switch error {
        case AuthError.signedOut:
            handleSignedOut(); return nil
        case AuthError.sessionChanged:
            return nil
        case let error as APIError:
            return error.message
        default:
            return fallback
        }
    }

    func signOut() async {
        await sessions.signOut()
        handleSignedOut()
    }

    private func handleSignedOut() {
        sessionEpoch += 1
        profile = nil
        flags = .unknown
        phase = .signedOut
    }
}

/// Stands in for the backend when none is configured: every call fails, so no screen can show
/// data (real or sample) in that state.
private struct UnconfiguredService: DincrService {
    struct NotConfigured: Error {}
    func me() async throws -> Profile { throw NotConfigured() }
    func completeProfileSetup(_ setup: ProfileSetup) async throws -> Profile { throw NotConfigured() }
    func freeDashboard() async throws -> FreeDashboard { throw NotConfigured() }
    func movements() async throws -> [Movement] { throw NotConfigured() }
    func create(_ kind: Movement.Kind, _ entry: EntryCreate, idempotencyKey: String) async throws { throw NotConfigured() }
    func update(movementID: String, _ update: MovementUpdate) async throws { throw NotConfigured() }
    func delete(movementID: String) async throws { throw NotConfigured() }
    func acceptLegal(_ request: LegalAcceptRequest) async throws -> LegalAcceptResult { throw NotConfigured() }
    func plans() async throws -> [PlanOption] { throw NotConfigured() }
    func billingCatalog() async throws -> BillingCatalog { throw NotConfigured() }
    func choosePlan(_ request: PlanChangeRequest) async throws -> PlanChangeResult { throw NotConfigured() }
    func featureFlags() async throws -> FeatureFlags { throw NotConfigured() }
    func deleteAccount() async throws { throw NotConfigured() }
    func debts() async throws -> [Debt] { throw NotConfigured() }
    func payDebt(id: Int, amount: Decimal, idempotencyKey: String) async throws -> DebtPaymentResult { throw NotConfigured() }
    func goals() async throws -> [Goal] { throw NotConfigured() }
    func contribute(goalID: Int, _ contribution: GoalContribution, idempotencyKey: String) async throws -> Goal { throw NotConfigured() }
}
