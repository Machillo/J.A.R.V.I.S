package com.dincr.app

import android.app.Application
import android.content.Intent
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.dincr.data.ApiClient
import com.dincr.data.ApiError
import com.dincr.data.AppLanguage
import com.dincr.data.AuthException
import com.dincr.data.DincrService
import com.dincr.data.FixtureDincrService
import com.dincr.data.InMemorySessionStore
import com.dincr.data.LiveDincrService
import com.dincr.data.MoneyFormat
import com.dincr.data.OAuthProvider
import com.dincr.data.Pkce
import com.dincr.data.Profile
import com.dincr.data.SessionManager
import com.dincr.data.SupabaseAuthClient
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/**
 * Build/launch configuration. No backend configured, or the `dincrFixtures` extra in a debug
 * build (UI tests) → fixture data. MainActivity is exported, so a release build ignores the
 * extra: no other app can point DINCR at sample data.
 */
sealed interface AppEnvironment {
    data class Live(val apiUrl: String, val supabaseUrl: String, val anonKey: String) : AppEnvironment
    data class Fixtures(val scenario: FixtureDincrService.Scenario, val skipLogin: Boolean, val latencyMs: Long = 350) : AppEnvironment

    companion object {
        /** The prototype's own redirect (never the store app's com.dincr.app://auth/callback). */
        const val AUTH_REDIRECT = "com.dincr.app.nativedev://auth/callback"

        fun from(intent: Intent?, allowLaunchFixtures: Boolean = BuildConfig.DEBUG): AppEnvironment {
            intent?.takeIf { allowLaunchFixtures }?.getStringExtra("dincrFixtures")?.let { raw ->
                val scenario = FixtureDincrService.Scenario.entries.firstOrNull { it.name.equals(raw, ignoreCase = true) }
                    ?: FixtureDincrService.Scenario.POPULATED
                // UI tests pass dincrLatencyMs=0: Compose's test dispatcher does not advance simulated network delays.
                return Fixtures(scenario, intent.getBooleanExtra("dincrSkipLogin", false), intent.getLongExtra("dincrLatencyMs", 350))
            }
            val api = BuildConfig.DINCR_API_URL
            val supabase = BuildConfig.DINCR_SUPABASE_URL
            val key = BuildConfig.DINCR_SUPABASE_ANON_KEY
            return if (api.isBlank() || supabase.isBlank() || key.isBlank()) Fixtures(FixtureDincrService.Scenario.POPULATED, false)
            else Live(api, supabase, key)
        }
    }
}

/** Gate order from CURRENT_STATE_AUDIT.md §1, same as the iOS AppModel. */
sealed interface Phase {
    data object Booting : Phase
    data object SignedOut : Phase
    data object LoadingIdentity : Phase
    data class IdentityError(val message: String) : Phase
    data object OwnerNotSupported : Phase
    data class NotYetSupported(val message: String) : Phase
    data object ProfileSetup : Phase
    data object Ready : Phase
}

class AppModel(application: Application) : AndroidViewModel(application) {
    private val _phase = MutableStateFlow<Phase>(Phase.Booting)
    val phase: StateFlow<Phase> = _phase.asStateFlow()
    private val _profile = MutableStateFlow<Profile?>(null)
    val profile: StateFlow<Profile?> = _profile.asStateFlow()
    private val _signInError = MutableStateFlow<String?>(null)
    val signInError: StateFlow<String?> = _signInError.asStateFlow()
    private val _signingIn = MutableStateFlow(false)
    val signingIn: StateFlow<Boolean> = _signingIn.asStateFlow()

    lateinit var environment: AppEnvironment private set
    lateinit var service: DincrService private set
    private var auth: SupabaseAuthClient? = null
    private lateinit var sessions: SessionManager
    private var pendingPkce: Pkce? = null
    private val language get() = AppLanguage.current()

    val isFixtures get() = environment is AppEnvironment.Fixtures
    val moneyFormat get() = MoneyFormat.from(_profile.value)

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
                service = LiveDincrService(ApiClient(environment.apiUrl, sessions))
            }
            is AppEnvironment.Fixtures -> {
                sessions = SessionManager(null, InMemorySessionStore())
                service = FixtureDincrService(environment.scenario, environment.latencyMs)
            }
        }
        viewModelScope.launch {
            when {
                environment is AppEnvironment.Fixtures && environment.skipLogin -> loadIdentity()
                environment is AppEnvironment.Fixtures -> _phase.value = Phase.SignedOut
                sessions.hasSession -> loadIdentity()
                else -> _phase.value = Phase.SignedOut
            }
        }
    }

    /** URL for the Custom Tab, or null in fixture mode. */
    fun beginSignIn(provider: OAuthProvider): String? {
        _signInError.value = null
        val client = auth ?: return null
        return Pkce.generate().also { pendingPkce = it }.let { client.authorizeUrl(provider, AppEnvironment.AUTH_REDIRECT, it) }
    }

    /** The browser could not be opened: nothing is pending any more. */
    fun signInFailed() {
        pendingPkce = null
        _signInError.value = language.pick("No pudimos abrir el navegador para iniciar sesión.", "We couldn’t open the browser to sign in.")
    }

    fun handleCallback(uri: String) {
        val client = auth ?: return
        val pkce = pendingPkce
        if (pkce == null) {
            // No sign-in in progress (a replayed or foreign link, or the process restarted while
            // the browser was open): nothing is exchanged. Ask for a fresh attempt.
            _signInError.value = language.pick("No pudimos completar el acceso. Intentá nuevamente.", "We couldn’t sign you in. Please try again.")
            return
        }
        pendingPkce = null
        viewModelScope.launch {
            _signingIn.value = true
            try {
                val code = SupabaseAuthClient.authorizationCode(uri, AppEnvironment.AUTH_REDIRECT)
                sessions.accept(client.exchange(code, pkce.verifier))
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
        loadIdentity()
        _signingIn.value = false
    }

    fun retryIdentity() = viewModelScope.launch { loadIdentity() }

    suspend fun loadIdentity() {
        if (_profile.value == null) _phase.value = Phase.LoadingIdentity
        try {
            apply(service.me())
        } catch (error: AuthException.SignedOut) {
            signedOut()
        } catch (error: ApiError) {
            _phase.value = Phase.IdentityError(error.message)
        }
    }

    fun apply(profile: Profile) {
        _profile.value = profile
        _phase.value = when {
            profile.isOwner -> Phase.OwnerNotSupported
            profile.legal?.required == true -> Phase.NotYetSupported(language.pick("Aceptá los términos actualizados desde la app actual de DINCR.", "Accept the updated terms in the current DINCR app."))
            profile.profileSetupCompleted != true -> Phase.ProfileSetup
            profile.planSelected != true -> Phase.NotYetSupported(language.pick("Elegí tu plan desde la app actual de DINCR.", "Choose your plan in the current DINCR app."))
            else -> Phase.Ready
        }
    }

    fun signOut() = viewModelScope.launch {
        sessions.signOut()
        signedOut()
    }

    private fun signedOut() {
        _profile.value = null
        _phase.value = Phase.SignedOut
    }
}

/** Short bilingual copy helper, same contract as the web `tx(es, en)` (prototype only). */
fun tx(spanish: String, english: String) = AppLanguage.current().pick(spanish, english)
