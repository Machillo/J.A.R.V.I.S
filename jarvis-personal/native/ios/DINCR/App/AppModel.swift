import DincrCore
import Foundation
import Observation

/// Session and identity state. Reproduces the Capacitor gate order (App.jsx): session → release
/// policy → identity → Owner boundary → legal → profile setup → plan → app lock → app.
@MainActor @Observable
final class AppModel {
    enum Phase: Equatable {
        case booting
        /// No usable backend configuration: nothing loads, and no sample data stands in for it.
        case unconfigured(LaunchPolicy.Reason)
        case signedOut
        case loadingIdentity
        /// `deletionPending`: `/auth/me` answered `account_deletion_pending` (A6).
        case identityError(String, deletionPending: Bool)
        /// A1 — this version is no longer supported.
        case updateRequired(ReleasePolicy)
        case unsupportedRole
        /// A8 — updated terms or privacy policy must be accepted before anything else.
        case legalRequired
        /// A11 — first plan choice.
        case choosePlan
        case profileSetup
        case ready
    }

    /// Schemes of the mail OAuth return (`<scheme>://gmail/callback`). The backend sends one global
    /// return URL (`FINVA_GMAIL_RETURN_URL`, default `com.finva.app`); both are claimed, like the
    /// Capacitor app, until that setting moves to `com.dincr.app`.
    static let mailReturnSchemes: Set<String> = ["com.dincr.app", "com.finva.app"]
    /// The scheme the backend uses today; `ASWebAuthenticationSession` waits for it.
    static let mailCallbackScheme = "com.finva.app"

    private(set) var phase: Phase = .booting
    private(set) var profile: Profile?
    var signInError: String?
    private(set) var isSigningIn = false
    /// B4 — operational kill switches; unknown until loaded, which means each flag's safe default.
    private(set) var flags: FeatureFlags = .unknown
    /// B7 — service health; nil when unknown (no banner).
    private(set) var health: ServiceHealth?
    /// A1 — an optional update (dismissible banner).
    private(set) var optionalUpdate: ReleasePolicy?
    /// One-line confirmation or error shown app-wide (reviewed notice, connected mailbox…).
    var notice: String?
    /// A tab or screen to open (for example after a mail connection completes).
    var pendingRoute: String?
    /// The outcome of the last mail connection, for the Email Monitor screen.
    private(set) var mailOutcome: String?
    /// Whether `mailOutcome` is a failure of the connection (technical-error look) or a neutral notice.
    private(set) var mailOutcomeIsFailure = true
    var planTier: PlanTier { profile?.planTier ?? .free }

    let service: DincrService
    /// The Owner's JARVIS chat for this session only; emptied on sign-out and whenever the
    /// identity is no longer the Owner.
    let jarvisChat: JarvisChatSession
    let environment: AppEnvironment
    let appLock: AppLock
    private let sessions: SessionManager
    private let auth: SupabaseAuthClient?
    private var pendingPKCE: PKCE?
    /// Changes on every sign-in and sign-out. An answer that arrives after the session it was asked
    /// for is gone belongs to nobody: it never shows one account's data to the next account.
    private var sessionEpoch = 0
    /// Screens capture this before a call and pass it to `message(for:epoch:fallback:)`.
    var currentEpoch: Int { sessionEpoch }
    private var handledMailReturns: HandledReturns
    /// A mail return whose completion failed transiently (offline): retried on resume.
    private var retryMailReturn: MailReturn?
    private var lastIdentityRefresh = Date.distantPast
    /// One identity-and-switches refresh at a time, whichever tab asked for it (B17).
    @ObservationIgnored private let accessRefresh = SingleFlight()
    private var releaseChecked = false

    init(environment: AppEnvironment = .current()) {
        self.environment = environment
        self.appLock = AppLock()
        self.handledMailReturns = HandledReturns(UserDefaults.standard.stringArray(forKey: "dincr.mailReturns") ?? [])
        let service: DincrService
        switch environment.mode {
        case let .live(apiURL, supabaseURL, anonKey):
            let auth = SupabaseAuthClient(projectURL: supabaseURL, anonKey: anonKey)
            let sessions = SessionManager(auth: auth, store: KeychainSessionStore())
            self.auth = auth
            self.sessions = sessions
            service = DincrService(client: APIClient(baseURL: apiURL, tokens: sessions))
        case let .fixtures(scenario, plan, role):
            self.auth = nil
            self.sessions = SessionManager(auth: nil, store: InMemorySessionStore())
            let latency: Duration = ProcessInfo.processInfo.arguments.contains("-DincrDisableAnimations") ? .milliseconds(50) : .milliseconds(300)
            // `-DincrRefreshFails`: a pull to refresh finds the server unreachable (B17 UI tests).
            let refreshFails = ProcessInfo.processInfo.arguments.contains("-DincrRefreshFails")
            // `-DincrLegalLapses`: the terms change while the app is open (SEC-01 UI tests).
            let legalLapses = ProcessInfo.processInfo.arguments.contains("-DincrLegalLapses")
            service = FixtureBackend.service(FixtureBackend(scenario: scenario, plan: plan, role: role, latency: latency,
                                                            identityRefreshFails: refreshFails, legalLapses: legalLapses))
        case let .unconfigured(reason):
            self.auth = nil
            self.sessions = SessionManager(auth: nil, store: InMemorySessionStore())
            service = DincrService(client: APIClient(baseURL: FixtureBackend.baseURL, tokens: FixtureTokens(), transport: UnconfiguredTransport()))
            self.phase = .unconfigured(reason)
        }
        self.service = service
        self.jarvisChat = JarvisChatSession { message in try await service.jarvisChat(message) }
    }

    var language: AppLanguage { .current }
    var moneyFormat: MoneyFormat { MoneyFormat(profile: profile) }
    var appVersion: String { Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0" }

    func start() async {
        if case .unconfigured = environment.mode { return }
        await sessions.setSignedOutHandler { [weak self] in
            Task { @MainActor in self?.handleSignedOut() }
        }
        if await checkReleasePolicy() { return }
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
            // A mail return delivered during boot belongs to no session: drop it.
            retryMailReturn = nil
        }
    }

    // MARK: Lifecycle

    func onForeground() async {
        appLock.onForeground()
        guard phase == .ready else { return }
        await refreshFlags()
        if let pending = retryMailReturn { await handleMailReturn(pending) }
        // A14 — refresh the identity at most every 15 s (plan or legal changes elsewhere).
        if Date.now.timeIntervalSince(lastIdentityRefresh) > 15 {
            lastIdentityRefresh = .now
            await loadIdentity()
        }
    }

    func onBackground() { appLock.onBackground() }

    /// A1 — fail open: any error or timeout lets the app start. Returns true when blocked.
    private func checkReleasePolicy() async -> Bool {
        guard !releaseChecked else { return false }
        releaseChecked = true
        let service = self.service
        let version = appVersion
        let policy = await withTaskGroup(of: ReleasePolicy?.self) { group in
            group.addTask { try? await service.releasePolicy(version: version) }
            group.addTask { try? await Task.sleep(for: .seconds(8)); return nil }
            let first = await group.next() ?? nil
            group.cancelAll()
            return first
        }
        if let policy, policy.isRequired { phase = .updateRequired(policy); return true }
        if let policy, policy.isOptional { optionalUpdate = policy }
        return false
    }

    func dismissOptionalUpdate() { optionalUpdate = nil }

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

    /// Cancelling the provider window is not a sign-out and not an error.
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

    /// Reads the identity and applies it; returns whether it was applied.
    @discardableResult
    func loadIdentity() async -> Bool {
        let epoch = sessionEpoch
        if profile == nil { phase = .loadingIdentity }
        do {
            let loaded = try await service.me()
            guard epoch == sessionEpoch else { return false }
            apply(loaded)
            return true
        } catch AuthError.signedOut {
            if epoch == sessionEpoch { handleSignedOut() }
        } catch AuthError.sessionChanged {
            // The session was replaced or closed while loading; its phase is already set.
        } catch is CancellationError {
            return false
        } catch let error as APIError {
            guard epoch == sessionEpoch else { return false }
            let deletionPending = error.code == "account_deletion_pending"
            // A background refresh of a signed-in app (resume) that fails for a transient reason
            // (offline, timeout, 5xx) keeps the user where they were; any other answer moves the gate.
            if phase == .ready, profile != nil, !deletionPending, error.isTransient { return false }
            phase = .identityError(error.message, deletionPending: deletionPending)
        } catch {
            guard epoch == sessionEpoch else { return false }
            phase = .identityError(language.pick("No pudimos cargar tu cuenta.", "We couldn’t load your account."), deletionPending: false)
        }
        return false
    }

    func apply(_ profile: Profile) {
        let wasReady = phase == .ready
        // Another account, or an account that is no longer the Owner, never sees this chat.
        if profile.id != self.profile?.id || !Jarvis.isAvailable(to: profile) { jarvisChat.reset() }
        self.profile = profile
        lastIdentityRefresh = .now
        switch IdentityGate.of(profile) {
        case .unsupportedRole:
            phase = .unsupportedRole
        case .legalRequired:
            phase = .legalRequired
        case .profileSetup:
            phase = .profileSetup
        case .choosePlan:
            phase = .choosePlan
        case .ready:
            phase = .ready
            if !wasReady {
                appLock.attach(userID: profile.id)
                Task {
                    await refreshFlags()
                    // A mail return that arrived before the app was ready (cold start) is redeemed now.
                    if let pending = retryMailReturn { await handleMailReturn(pending) }
                }
            }
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
            if let message = result.message, !message.isEmpty { notice = message }
            return nil
        } catch {
            return message(for: error, epoch: epoch, fallback: language.pick("No pudimos guardar tu suscripción.", "We couldn’t save your subscription."))
        }
    }

    /// Returns whether the switches were read.
    @discardableResult
    func refreshFlags() async -> Bool {
        let epoch = sessionEpoch
        // A failed load keeps the last known flags (or the safe defaults); it never enables anything.
        let loaded = try? await service.featureFlags()
        if let loaded, epoch == sessionEpoch { flags = loaded }
        if let health = try? await service.health(), epoch == sessionEpoch { self.health = health }
        return loaded != nil
    }

    // MARK: Pull to refresh (B17)

    /// A pull to refresh on Plan, Patrimonio or Perfil: the identity (plan and role) and the switches
    /// read again, plus the tab's own `extra` read (Patrimonio's debts). Nothing on screen is emptied
    /// when it fails: the notice says the information is the previous one. Returns whether everything
    /// was read. Android: `AppModel.refreshTab`.
    @discardableResult
    func refreshTab(_ extra: (@MainActor () async -> Bool)? = nil) async -> Bool {
        let epoch = sessionEpoch
        async let access = accessRefresh.run { await self.refreshAccess() }
        let more = await extra?() ?? true
        let read = await access
        let ok = read && more
        if !ok, epoch == sessionEpoch, phase == .ready { notice = PullRefresh.failureNotice(language) }
        return ok
    }

    private func refreshAccess() async -> Bool {
        async let flags = refreshFlags()
        let identity = await loadIdentity()
        let switches = await flags
        return switches && identity
    }

    /// G9 / A6 — the backend schedules the deletion; this device then forgets the session.
    func deleteAccount() async -> String? {
        if profile?.canDeleteAccountInApp == false {
            return language.pick("La cuenta Owner no se elimina desde la app.", "The Owner account can’t be deleted from the app.")
        }
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
        case AuthError.sessionChanged, is CancellationError:
            return nil
        case let error as APIError:
            if error.kind == .featureUnavailable { Task { await refreshFlags() } }
            // SEC-01: the server's legal gate refused the call (the terms changed while the app was
            // open). Reading the identity again moves the gate to the acceptance screen.
            if error.code == APIError.legalAcceptanceRequiredCode { Task { await loadIdentity() } }
            return error.message
        default:
            return fallback
        }
    }

    // MARK: Email Monitor return (H3)

    /// A `<scheme>://gmail/callback?…` URL, from the authentication session or opened by the system.
    /// Returns true when it was a mail return (handled or ignored), false for any other URL.
    @discardableResult
    func handleOpenURL(_ url: URL) async -> Bool {
        guard let mailReturn = MailReturn.parse(url, schemes: Self.mailReturnSchemes) else { return false }
        await handleMailReturn(mailReturn)
        return true
    }

    func handleMailReturn(_ mailReturn: MailReturn) async {
        // Each browser return is redeemed once, even when delivered twice.
        guard !handledMailReturns.contains(mailReturn.key) else { return }
        guard mailReturn.isAuthorized, let flow = mailReturn.flow, let completion = mailReturn.completion else {
            remember(mailReturn)
            mailOutcome = MailReturn.message(mailReturn.status, language: language)
            mailOutcomeIsFailure = MailReturn.isFailure(mailReturn.status)
            pendingRoute = "mail"
            return
        }
        guard phase == .ready else {
            // Cold start (booting, loading the identity) or a gate: kept and redeemed once ready. With no
            // session at all it is dropped (`start()` and sign-out clear it), never kept for a later sign-in.
            if phase != .signedOut { retryMailReturn = mailReturn }
            return
        }
        let epoch = sessionEpoch
        do {
            _ = try await service.completeMailConnection(flow: flow, completion: completion)
            guard epoch == sessionEpoch else { return }
            remember(mailReturn)
            retryMailReturn = nil
            mailOutcome = nil
            notice = language.pick("Tu correo quedó conectado.", "Your mail is connected.")
            pendingRoute = "mail"
        } catch let error as APIError where error.isTransient {
            // The session may have ended while the request was in flight: a return belongs only to the
            // session that started it, so it is never kept for the next account.
            guard epoch == sessionEpoch else { return }
            // Offline or a server hiccup: the one-time completion stays valid for a while; retry on resume.
            retryMailReturn = mailReturn
            mailOutcome = error.message
            mailOutcomeIsFailure = true
        } catch {
            remember(mailReturn)
            retryMailReturn = nil
            mailOutcome = message(for: error, epoch: epoch, fallback: MailReturn.message("error", language: language))
            mailOutcomeIsFailure = true
            pendingRoute = "mail"
        }
    }

    func consumeMailOutcome() { mailOutcome = nil }

    /// Retries a mail connection whose completion failed transiently (the outcome banner's action).
    func retryPendingMailReturn() async {
        if let pending = retryMailReturn { await handleMailReturn(pending) }
    }
    var hasPendingMailReturn: Bool { retryMailReturn != nil }

    private func remember(_ mailReturn: MailReturn) {
        handledMailReturns.add(mailReturn.key)
        UserDefaults.standard.set(handledMailReturns.keys, forKey: "dincr.mailReturns")
    }

    // MARK: Sign out

    func signOut() async {
        await sessions.signOut()
        handleSignedOut()
    }

    private func handleSignedOut() {
        sessionEpoch += 1
        profile = nil
        flags = .unknown
        health = nil
        notice = nil
        pendingRoute = nil
        mailOutcome = nil
        retryMailReturn = nil
        appLock.detach()
        DataExport.clear()
        jarvisChat.reset()
        phase = .signedOut
    }
}

/// Stands in for the network when no backend is configured: every call fails, so no screen can
/// show data (real or sample) in that state.
private struct UnconfiguredTransport: HTTPTransport {
    func send(_ request: URLRequest) async throws -> (Data, HTTPURLResponse) { throw URLError(.cannotConnectToHost) }
}
