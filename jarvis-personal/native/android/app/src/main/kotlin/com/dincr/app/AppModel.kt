package com.dincr.app

import android.app.Application
import android.content.Context
import android.content.Intent
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.dincr.data.ApiClient
import com.dincr.data.ApiError
import com.dincr.data.AppLanguage
import com.dincr.data.AuthException
import com.dincr.data.AuthSession
import com.dincr.data.DincrApi
import com.dincr.data.FakeBackend
import com.dincr.data.FeatureFlags
import com.dincr.data.HandledReturns
import com.dincr.data.IdentityGate
import com.dincr.data.InMemorySessionStore
import com.dincr.data.Jarvis
import com.dincr.data.JarvisChatSession
import com.dincr.data.LaunchPolicy
import com.dincr.data.MailReturn
import com.dincr.data.MoneyFormat
import com.dincr.data.OAuthProvider
import com.dincr.data.OpsFlag
import com.dincr.data.PlanTier
import com.dincr.data.Pkce
import com.dincr.data.ProductEvent
import com.dincr.data.PullRefresh
import com.dincr.data.Profile
import com.dincr.data.ReleasePolicy
import com.dincr.data.ServiceHealth
import com.dincr.data.SessionManager
import com.dincr.data.SingleFlight
import com.dincr.data.SupabaseAuthClient
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

/**
 * Build/launch configuration, decided by [LaunchPolicy]. Fixture data only in a debug build and
 * only when asked for (the `dincrFixtures` extra of the UI tests, or `dincr.fixtures=true` in
 * local.properties). MainActivity is exported, so a release build ignores every extra: no other
 * app can point DINCR at sample data. Without a complete HTTPS backend configuration the app
 * shows [Phase.Unconfigured] instead of silently running on fixtures.
 */
sealed interface AppEnvironment {
    data class Live(val apiUrl: String, val supabaseUrl: String, val anonKey: String) : AppEnvironment
    data class Fixtures(
        val scenario: FakeBackend.Scenario, val plan: PlanTier, val skipLogin: Boolean, val latencyMs: Long = 350,
        /** The role the fake server answers in /auth/me (role-matrix UI tests); never a live session's. */
        val role: FakeBackend.Role = FakeBackend.Role.USER,
        /** `dincrRefreshFails`: a pull to refresh finds the server unreachable (B17 UI tests). */
        val identityRefreshFails: Boolean = false,
    ) : AppEnvironment
    data class Unconfigured(val reason: LaunchPolicy.Reason) : AppEnvironment

    companion object {
        /** This identity's own redirect (`com.dincr.app://auth/callback` for the DINCR app id). */
        val AUTH_REDIRECT: String get() = BuildConfig.AUTH_REDIRECT

        /** Schemes the backend may send a finished mail connection to (FINVA_GMAIL_RETURN_URL). */
        val MAIL_SCHEMES: Set<String> get() = if (BuildConfig.APPLICATION_ID == "com.dincr.app") setOf("com.dincr.app", "com.finva.app") else setOf(BuildConfig.APPLICATION_ID)

        fun from(intent: Intent?, debugBuild: Boolean = BuildConfig.DEBUG): AppEnvironment {
            val launchFixtures = if (debugBuild) intent?.getStringExtra("dincrFixtures") else null
            val decision = LaunchPolicy.decide(debugBuild, launchFixtures, BuildConfig.DINCR_FIXTURES,
                BuildConfig.DINCR_API_URL, BuildConfig.DINCR_SUPABASE_URL, BuildConfig.DINCR_SUPABASE_ANON_KEY)
            return when (decision) {
                is LaunchPolicy.Decision.Live -> Live(decision.apiUrl, decision.supabaseUrl, decision.anonKey)
                is LaunchPolicy.Decision.Unconfigured -> Unconfigured(decision.reason)
                is LaunchPolicy.Decision.Fixtures -> Fixtures(
                    FakeBackend.Scenario.entries.firstOrNull { it.name.equals(decision.scenario, ignoreCase = true) } ?: FakeBackend.Scenario.POPULATED,
                    PlanTier.from(intent?.getStringExtra("dincrPlan")),
                    intent?.getBooleanExtra("dincrSkipLogin", false) ?: false,
                    // UI tests pass dincrLatencyMs=0: Compose's test dispatcher does not advance simulated network delays.
                    intent?.getLongExtra("dincrLatencyMs", 350) ?: 350,
                    FakeBackend.Role.entries.firstOrNull { it.wire == intent?.getStringExtra("dincrRole") } ?: FakeBackend.Role.USER,
                    intent?.getBooleanExtra("dincrRefreshFails", false) ?: false,
                )
            }
        }
    }
}

/** Gate order of the Capacitor app (CURRENT_STATE_AUDIT.md §1), same as the iOS AppModel. */
sealed interface Phase {
    data object Booting : Phase
    /** No usable backend configuration: nothing loads, and no sample data stands in for it. */
    data class Unconfigured(val reason: LaunchPolicy.Reason) : Phase
    data object SignedOut : Phase
    data object LoadingIdentity : Phase
    data class IdentityError(val message: String, val deletionPending: Boolean = false) : Phase
    data class UpdateRequired(val policy: ReleasePolicy) : Phase
    data object UnsupportedRole : Phase
    data object LegalRequired : Phase
    data object ProfileSetup : Phase
    data object ChoosePlan : Phase
    data object Ready : Phase
}

/** Cache folder of the data export (also declared in res/xml/file_paths.xml). */
const val EXPORT_DIR = "export"

class AppModel(application: Application) : AndroidViewModel(application) {
    private val _phase = MutableStateFlow<Phase>(Phase.Booting)
    val phase: StateFlow<Phase> = _phase.asStateFlow()
    private val _profile = MutableStateFlow<Profile?>(null)
    val profile: StateFlow<Profile?> = _profile.asStateFlow()
    private val _signInError = MutableStateFlow<String?>(null)
    val signInError: StateFlow<String?> = _signInError.asStateFlow()
    private val _signingIn = MutableStateFlow(false)
    val signingIn: StateFlow<Boolean> = _signingIn.asStateFlow()
    private val _flags = MutableStateFlow(FeatureFlags())
    /** Operational kill switches; until loaded, every flag is at its safe default. */
    val flags: StateFlow<FeatureFlags> = _flags.asStateFlow()
    private val _health = MutableStateFlow<ServiceHealth?>(null)
    val health: StateFlow<ServiceHealth?> = _health.asStateFlow()
    private val _release = MutableStateFlow<ReleasePolicy?>(null)
    val release: StateFlow<ReleasePolicy?> = _release.asStateFlow()
    private val _notice = MutableStateFlow<String?>(null)
    /** One-time message for the main screen (mail connected, plan changed…). */
    val notice: StateFlow<String?> = _notice.asStateFlow()
    private val _pendingRoute = MutableStateFlow<String?>(null)
    /** A screen the app should open next (e.g. mail after a connection returns). */
    val pendingRoute: StateFlow<String?> = _pendingRoute.asStateFlow()

    lateinit var environment: AppEnvironment private set
    lateinit var api: DincrApi private set
    /** Fixture sessions only: the fake server (B17 UI tests count the reads a pull to refresh makes). */
    var fixtureBackend: FakeBackend? = null
        private set
    /** The Owner's JARVIS chat for this session only; emptied on sign-out and whenever the identity is no longer the Owner. */
    val jarvisChat = JarvisChatSession({ message -> api.jarvisChat(message) })
    val appLock = AppLock(application)
    private var auth: SupabaseAuthClient? = null
    private lateinit var sessions: SessionManager
    private val pendingSignIn = PendingSignInStore(application)
    private var fixturePkce: Pkce? = null
    private val prefs = application.getSharedPreferences("dincr.preferences", Context.MODE_PRIVATE)

    init {
        // A data export left over from an earlier session (or a crash) is removed at startup.
        clearExports()
    }
    private val handledMail = HandledReturns(prefs.getString("mail_returns", "").orEmpty().split('\n').filter { it.isNotEmpty() })
    private val language get() = AppLanguage.current()
    private var lastIdentityRefresh = 0L
    private var flagLoop: Job? = null

    val isFixtures get() = environment is AppEnvironment.Fixtures
    val moneyFormat get() = MoneyFormat.from(_profile.value)
    val plan: PlanTier get() = _profile.value?.planTier ?: PlanTier.FREE
    val appVersion: String get() = BuildConfig.VERSION_NAME

    fun isOn(flag: OpsFlag): Boolean = _flags.value.isEnabled(flag)

    private var store: StoreBilling? = null

    /**
     * G3 — Play Billing lives as long as this model, not a screen: a purchase verification is never
     * cancelled by leaving the plans screen, and the client is closed with the model.
     */
    fun storeBilling(): StoreBilling = store ?: StoreBilling(getApplication(), api, viewModelScope) { showNotice(it) }.also { store = it }

    /**
     * Sends purchases Google Play has and the backend never confirmed (a pending payment that
     * completed later, or a purchase interrupted by process death) for verification. Only the
     * backend acknowledges and grants a plan.
     */
    private fun reconcileStore() {
        if (_phase.value is Phase.Ready && !isFixtures && isOn(OpsFlag.STORE_BILLING)) storeBilling().reconcile()
    }

    override fun onCleared() {
        store?.close()
        super.onCleared()
    }
    fun consumeNotice() { _notice.value = null }
    fun consumeRoute() { _pendingRoute.value = null }
    fun showNotice(message: String) { _notice.value = message }

    /**
     * Runs [block] for a screen and maps every failure to a message it can show. A rejected
     * session signs out (instead of crashing the screen that noticed it); cancellation passes.
     */
    suspend fun <T> load(fallback: String, block: suspend () -> T): Result<T> = try {
        Result.success(block())
    } catch (error: CancellationException) {
        throw error
    } catch (error: AuthException.SignedOut) {
        signedOut()
        Result.failure(error)
    } catch (error: ApiError) {
        if (error.kind == ApiError.Kind.FEATURE_UNAVAILABLE) viewModelScope.launch { refreshFlags() }
        Result.failure(error)
    } catch (error: Exception) {
        Result.failure(IllegalStateException(fallback))
    }

    /** Called once from the activity with its launch intent. */
    fun configure(environment: AppEnvironment) {
        if (this::environment.isInitialized) return
        this.environment = environment
        when (environment) {
            is AppEnvironment.Live -> {
                val client = SupabaseAuthClient(environment.supabaseUrl, environment.anonKey)
                auth = client
                sessions = SessionManager(client, KeystoreSessionStore(getApplication())) { viewModelScope.launch { signedOut() } }
                api = DincrApi(ApiClient(environment.apiUrl, sessions))
            }
            is AppEnvironment.Fixtures -> {
                sessions = SessionManager(null, InMemorySessionStore(if (environment.skipLogin) FIXTURE_SESSION else null))
                val backend = FakeBackend(environment.scenario, environment.plan, environment.latencyMs, role = environment.role,
                    identityRefreshFails = environment.identityRefreshFails)
                fixtureBackend = backend
                api = DincrApi(ApiClient("https://fixtures.invalid", sessions, backend))
            }
            is AppEnvironment.Unconfigured -> {
                _phase.value = Phase.Unconfigured(environment.reason)
                return
            }
        }
        viewModelScope.launch {
            checkReleasePolicy()
            if (sessions.hasSession) loadIdentity() else _phase.value = Phase.SignedOut
        }
    }

    // --- Lifecycle ----------------------------------------------------------------------------------

    /** App came to the foreground: re-check the release policy, flags, identity (throttled), lock. */
    fun onForeground() {
        appLock.onForeground()
        if (!this::environment.isInitialized || environment is AppEnvironment.Unconfigured) return
        viewModelScope.launch {
            checkReleasePolicy()
            if (_phase.value is Phase.Ready) {
                refreshFlags()
                reconcileStore()
                val now = System.currentTimeMillis()
                if (now - lastIdentityRefresh > IDENTITY_THROTTLE_MS) { lastIdentityRefresh = now; loadIdentity() }
            }
        }
        startFlagLoop()
    }

    fun onBackground() {
        appLock.onBackground()
        flagLoop?.cancel()
        flagLoop = null
    }

    private fun startFlagLoop() {
        if (flagLoop?.isActive == true) return
        flagLoop = viewModelScope.launch {
            while (isActive) {
                delay(FLAG_REFRESH_MS)
                if (_phase.value is Phase.Ready) refreshFlags()
            }
        }
    }

    /** Fail-open, 8 s: an unreachable policy never blocks the app. */
    private suspend fun checkReleasePolicy() {
        val policy = withTimeoutOrNull(8_000) { runCatching { api.releasePolicy(appVersion) }.getOrNull() } ?: return
        _release.value = policy
        val current = _phase.value
        if (policy.isRequired && _profile.value?.hasUnsupportedRole != true) _phase.value = Phase.UpdateRequired(policy)
        else if (current is Phase.UpdateRequired) { if (_profile.value != null) apply(_profile.value!!) else _phase.value = if (sessions.hasSession) Phase.LoadingIdentity else Phase.SignedOut }
    }

    fun recheckRelease() = viewModelScope.launch { checkReleasePolicy() }

    /** Returns whether the switches were read; a failed read keeps the last known ones. */
    suspend fun refreshFlags(): Boolean {
        val loaded = runCatching { api.featureFlags() }.onSuccess { _flags.value = it }.isSuccess
        runCatching { api.health() }.onSuccess { _health.value = it }
        return loaded
    }

    // --- Pull to refresh (B17) ---------------------------------------------------------------------------

    /** One identity-and-switches refresh at a time, whichever tab asked for it. */
    private val accessRefresh = SingleFlight(viewModelScope)

    /**
     * B17 — a pull to refresh on Plan, Patrimonio or Perfil: the identity (plan and role) and the
     * switches read again, plus the tab's own [extra] read (Patrimonio's debts). Nothing on screen is
     * emptied when it fails: the notice says the information is the previous one. Returns whether
     * everything was read. iOS: `AppModel.refreshTab`.
     */
    suspend fun refreshTab(extra: (suspend () -> Boolean)? = null): Boolean = coroutineScope {
        val epoch = sessionEpoch
        val access = async { accessRefresh.run { refreshAccess() } }
        val more = extra?.invoke() ?: true
        val ok = access.await() && more
        if (!ok && epoch == sessionEpoch && _phase.value is Phase.Ready) showNotice(PullRefresh.failureNotice(language))
        ok
    }

    private suspend fun refreshAccess(): Boolean = coroutineScope {
        val flags = async { refreshFlags() }
        val identity = loadIdentity(keepOnTransient = true)
        flags.await() && identity
    }

    /** Optional update dismissed for this version (stored per latest version). */
    fun dismissOptionalUpdate() {
        _release.value?.latestVersion?.let { prefs.edit().putString("release_dismissed", it).apply() }
        _release.value = _release.value?.copy(status = "current")
    }

    val optionalUpdateDismissed: Boolean get() = _release.value?.latestVersion?.let { prefs.getString("release_dismissed", null) == it } ?: true

    // --- Sign in ---------------------------------------------------------------------------------------

    /** URL for the Custom Tab, or null in fixture mode. The verifier survives process death. */
    fun beginSignIn(provider: OAuthProvider): String? {
        _signInError.value = null
        val client = auth ?: return null
        val pkce = Pkce.generate()
        pendingSignIn.save(pkce)
        return client.authorizeUrl(provider, AppEnvironment.AUTH_REDIRECT, pkce)
    }

    /** The browser could not be opened: nothing is pending any more. */
    fun signInFailed() {
        pendingSignIn.clear()
        _signInError.value = language.pick("No pudimos abrir el navegador para iniciar sesión.", "We couldn’t open the browser to sign in.")
    }

    fun handleCallback(uri: String) {
        val client = auth ?: return
        // Validate the link before consuming the pending verifier: a foreign or malformed link must
        // not cancel a sign-in that is still in progress.
        val code = runCatching { SupabaseAuthClient.authorizationCode(uri, AppEnvironment.AUTH_REDIRECT) }.getOrNull()
        val pkce = if (code != null) pendingSignIn.take() else null
        if (code == null || pkce == null) {
            // No sign-in in progress (a replayed or foreign link, or it expired): nothing is
            // exchanged. Ask for a fresh attempt.
            _signInError.value = language.pick("No pudimos completar el acceso. Intentá nuevamente.", "We couldn’t sign you in. Please try again.")
            return
        }
        viewModelScope.launch {
            _signingIn.value = true
            try {
                sessions.accept(client.exchange(code, pkce.verifier))
                sessionEpoch += 1
                loadIdentity()
            } catch (error: CancellationException) {
                throw error
            } catch (error: Exception) {
                _signInError.value = language.pick("No pudimos completar el acceso. Intentá nuevamente.", "We couldn’t sign you in. Please try again.")
            } finally {
                _signingIn.value = false
            }
        }
    }

    fun signInWithFixtures() = viewModelScope.launch {
        _signingIn.value = true
        sessions.accept(FIXTURE_SESSION)
        sessionEpoch += 1
        loadIdentity()
        _signingIn.value = false
    }

    fun retryIdentity() = viewModelScope.launch { loadIdentity() }

    // JARVIS chat: sent from the model's scope, so leaving the screen never cuts a message in half.
    fun sendToJarvis(text: String) = viewModelScope.launch { jarvisChat.submit(text) }
    fun confirmJarvisChange() = viewModelScope.launch { jarvisChat.confirm() }
    fun cancelJarvisChange() = viewModelScope.launch { jarvisChat.cancel() }
    fun jarvisItIsTheAnswer() = viewModelScope.launch { jarvisChat.itIsTheAnswer() }
    fun jarvisAnotherRequest() = viewModelScope.launch { jarvisChat.anotherRequest() }
    fun retryJarvisMessage(id: Long) = viewModelScope.launch { jarvisChat.retry(id) }

    // --- Identity and gates ------------------------------------------------------------------------------

    /**
     * Changes on every sign-in and sign-out. An identity answer that arrives after the session it
     * was asked for is gone belongs to nobody: it never shows one account's name, formats or
     * gates to the next account (or after signing out).
     */
    private var sessionEpoch = 0

    /**
     * Reads the identity and applies it; returns whether it was applied. [keepOnTransient] (a pull
     * to refresh, B17): a signed-in app that fails for a transient reason (offline, timeout, 5xx)
     * keeps the user where they were, as iOS does; any other answer moves the gate as always.
     */
    suspend fun loadIdentity(keepOnTransient: Boolean = false): Boolean {
        val epoch = sessionEpoch
        if (_profile.value == null) _phase.value = Phase.LoadingIdentity
        try {
            val profile = api.me()
            if (epoch == sessionEpoch) { apply(profile); return true }
        } catch (error: CancellationException) {
            throw error
        } catch (error: AuthException.SignedOut) {
            if (epoch == sessionEpoch) signedOut()
        } catch (error: AuthException.SessionChanged) {
            // The session was replaced or closed while loading; its phase is already set.
        } catch (error: ApiError) {
            val deletionPending = error.code == "account_deletion_pending"
            val keep = keepOnTransient && _phase.value is Phase.Ready && _profile.value != null && !deletionPending && error.isTransient
            if (epoch == sessionEpoch && !keep) _phase.value = Phase.IdentityError(error.message, deletionPending)
        } catch (error: Exception) {
            if (epoch == sessionEpoch) _phase.value = Phase.IdentityError(language.pick("No pudimos cargar tu cuenta.", "We couldn’t load your account."))
        }
        return false
    }

    /** Applies an identity: the Owner boundary, then legal, profile setup and plan, in that order. */
    fun apply(profile: Profile) {
        val previous = _profile.value
        val wasReady = _phase.value is Phase.Ready
        // Another account, or an account that is no longer the Owner, never sees this chat.
        if (profile.id != previous?.id || !Jarvis.isAvailable(profile)) jarvisChat.reset()
        _profile.value = profile
        lastIdentityRefresh = System.currentTimeMillis()
        if (previous?.id != profile.id) appLock.attach(profile.id.toString())
        profile.subscription?.accessNotice?.let { notice -> notice.message?.let { _notice.value = listOfNotNull(notice.title, it).joinToString(". ") } }
        val release = _release.value
        _phase.value = if (release?.isRequired == true && !profile.hasUnsupportedRole) Phase.UpdateRequired(release) else when (IdentityGate.of(profile)) {
            // Only "user" and the single Owner are served; any other role is refused, never promoted.
            IdentityGate.UNSUPPORTED_ROLE -> Phase.UnsupportedRole
            IdentityGate.LEGAL_REQUIRED -> Phase.LegalRequired
            IdentityGate.PROFILE_SETUP -> Phase.ProfileSetup
            IdentityGate.CHOOSE_PLAN -> Phase.ChoosePlan
            IdentityGate.READY -> Phase.Ready
        }
        // The switches are read on becoming ready (as iOS); a ready app already reads them on resume, in
        // their loop and on a pull to refresh, so an identity read again does not read them twice.
        if (_phase.value is Phase.Ready) viewModelScope.launch { if (!wasReady) refreshFlags(); reconcileStore() }
    }

    /** `DELETE /auth/me` for an account whose deletion is pending (or requested now), then sign out. */
    suspend fun deleteAccount(): String? {
        if (_profile.value?.canDeleteAccountInApp == false) return language.pick("La cuenta Owner no se elimina desde la app.", "The Owner account can’t be deleted from the app.")
        return load(language.pick("No pudimos eliminar tu cuenta.", "We couldn’t delete your account.")) { api.deleteAccount() }
            .fold({ signOut(); null }, { it.message })
    }

    fun signOut() = viewModelScope.launch {
        sessions.signOut()
        signedOut()
    }

    /**
     * G8 — the JSON export is shared from the app cache; no copy outlives the session that made it
     * (startup, sign-out and account deletion remove it).
     */
    fun clearExports() {
        val dir = java.io.File(getApplication<Application>().cacheDir, EXPORT_DIR)
        viewModelScope.launch(kotlinx.coroutines.Dispatchers.IO) { dir.deleteRecursively() }
    }

    private fun signedOut() {
        clearExports()
        sessionEpoch += 1
        pendingSignIn.clear()
        appLock.detach()
        jarvisChat.reset()
        _profile.value = null
        _flags.value = FeatureFlags()
        _notice.value = null
        _pendingRoute.value = null
        _phase.value = Phase.SignedOut
    }

    // --- Mail connection return ------------------------------------------------------------------------

    /**
     * A mail connection came back from the browser. Parsed strictly, redeemed once (a handled
     * ledger survives restarts) and only with the current session; the backend refuses a flow
     * started by another account. Transient failures are retried; a definitive answer is final.
     */
    fun handleMailReturn(url: String) {
        val mail = MailReturn.parse(url, AppEnvironment.MAIL_SCHEMES) ?: return
        if (handledMail.contains(mail.key)) return
        _pendingRoute.value = "mail"
        if (!mail.isAuthorized) {
            markHandled(mail.key)
            if (mail.status != "already_processed") _notice.value = MailReturn.message(mail.status, language)
            return
        }
        viewModelScope.launch {
            var attempt = 0
            while (true) {
                try {
                    api.completeMailConnection(mail.flow!!, mail.completion!!)
                    markHandled(mail.key)
                    _notice.value = language.pick("Tu correo quedó conectado. Revisá los avisos detectados.", "Your mail is connected. Review the detected notices.")
                    return@launch
                } catch (error: CancellationException) {
                    throw error
                } catch (error: ApiError) {
                    if (error.isTransient && attempt < 3) { attempt += 1; delay(1_000L * attempt); continue }
                    if (!error.isTransient) markHandled(mail.key)
                    _notice.value = if (error.kind == ApiError.Kind.FORBIDDEN) language.pick("Esa conexión pertenece a otra cuenta DINCR.", "That connection belongs to another DINCR account.") else error.message
                    return@launch
                } catch (error: AuthException) {
                    _notice.value = language.pick("Iniciá sesión con la misma cuenta para terminar de conectar tu correo.", "Sign in with the same account to finish connecting your mail.")
                    return@launch
                }
            }
        }
    }

    private fun markHandled(key: String) {
        handledMail.add(key)
        prefs.edit().putString("mail_returns", handledMail.snapshot.joinToString("\n")).apply()
    }

    // --- Analytics (backend allow-list only; no personal data) ----------------------------------------

    fun recordScreen(eventName: String, surface: String) {
        if (eventName !in ProductEvent.ALLOWED || _phase.value !is Phase.Ready || isFixtures) return
        viewModelScope.launch { runCatching { api.recordEvent(ProductEvent(eventName, surface, true, appVersion)) } }
    }

    private companion object {
        const val IDENTITY_THROTTLE_MS = 15_000L
        const val FLAG_REFRESH_MS = 60_000L
        /** Synthetic session for fixture mode only (never sent anywhere real). */
        val FIXTURE_SESSION = AuthSession("fixture-access", "fixture-refresh", Long.MAX_VALUE / 2, "fixture-user")
    }
}

/** Short bilingual copy helper, same contract as the web `tx(es, en)`. */
fun tx(spanish: String, english: String) = AppLanguage.current().pick(spanish, english)
