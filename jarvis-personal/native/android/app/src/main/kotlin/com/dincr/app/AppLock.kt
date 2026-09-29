package com.dincr.app

import android.content.Context
import android.os.SystemClock
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricManager.Authenticators.BIOMETRIC_WEAK
import androidx.biometric.BiometricManager.Authenticators.DEVICE_CREDENTIAL
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import com.dincr.data.AppLockPolicy
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Local app lock, same behaviour as the Capacitor app (`lib/appLock.js`): opt-in per signed-in
 * user, unlocked with the phone's biometrics or its PIN/pattern/password, locked at launch and
 * after five minutes in the background. Time is measured with the monotonic clock, so changing the
 * phone's date cannot skip the lock. Nothing here is sent anywhere.
 */
class AppLock(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("dincr.preferences", Context.MODE_PRIVATE)
    private val biometrics = BiometricManager.from(context.applicationContext)
    private val _locked = MutableStateFlow(false)
    val locked: StateFlow<Boolean> = _locked.asStateFlow()
    private var userKey: String? = null
    private var backgroundedAt: Long? = null

    enum class Availability { AVAILABLE, NOT_ENROLLED, UNSUPPORTED }

    val availability: Availability
        get() = when (biometrics.canAuthenticate(BIOMETRIC_WEAK or DEVICE_CREDENTIAL)) {
            BiometricManager.BIOMETRIC_SUCCESS -> Availability.AVAILABLE
            BiometricManager.BIOMETRIC_ERROR_NONE_ENROLLED -> Availability.NOT_ENROLLED
            else -> Availability.UNSUPPORTED
        }

    val isEnabled: Boolean get() = userKey?.let { prefs.getBoolean("app_lock:$it", false) } ?: false
    val onboardingSeen: Boolean get() = userKey?.let { prefs.getBoolean("app_lock_offer:$it", false) } ?: true

    /** A user signed in (or the session was restored): lock now if they enabled it. */
    fun attach(userId: String?) {
        userKey = userId
        backgroundedAt = null
        _locked.value = isEnabled
    }

    fun detach() {
        userKey = null
        backgroundedAt = null
        _locked.value = false
    }

    fun setEnabled(enabled: Boolean) {
        val key = userKey ?: return
        prefs.edit().putBoolean("app_lock:$key", enabled).putBoolean("app_lock_offer:$key", true).apply()
        if (!enabled) _locked.value = false
    }

    fun markOnboardingSeen() {
        val key = userKey ?: return
        prefs.edit().putBoolean("app_lock_offer:$key", true).apply()
    }

    fun lockNow() { if (isEnabled) _locked.value = true }

    fun onBackground() { backgroundedAt = SystemClock.elapsedRealtime() }

    fun onForeground() {
        if (AppLockPolicy.shouldLock(isEnabled, backgroundedAt, SystemClock.elapsedRealtime())) _locked.value = true
        backgroundedAt = null
    }

    /** Shows the system prompt; [onResult] gets null on success or a message to show. */
    fun authenticate(activity: FragmentActivity, onResult: (String?) -> Unit) {
        val prompt = BiometricPrompt(activity, ContextCompat.getMainExecutor(activity), object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                _locked.value = false
                onResult(null)
            }

            override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                onResult(when (errorCode) {
                    BiometricPrompt.ERROR_USER_CANCELED, BiometricPrompt.ERROR_CANCELED, BiometricPrompt.ERROR_NEGATIVE_BUTTON -> tx("Desbloqueo cancelado.", "Unlock cancelled.")
                    BiometricPrompt.ERROR_LOCKOUT, BiometricPrompt.ERROR_LOCKOUT_PERMANENT -> tx("La biometría está bloqueada temporalmente. Usá el código del teléfono.", "Biometrics are temporarily locked. Use your phone passcode.")
                    BiometricPrompt.ERROR_NO_BIOMETRICS, BiometricPrompt.ERROR_NO_DEVICE_CREDENTIAL -> tx("El teléfono necesita un bloqueo de pantalla configurado.", "Your phone needs a screen lock.")
                    else -> tx("No pudimos verificar tu identidad. Intentá de nuevo.", "We couldn’t verify it’s you. Please try again.")
                })
            }
        })
        prompt.authenticate(
            BiometricPrompt.PromptInfo.Builder()
                .setTitle(tx("Desbloquear DINCR", "Unlock DINCR"))
                .setSubtitle(tx("Usá tu biometría o el bloqueo del teléfono", "Use your biometrics or your phone’s lock"))
                .setAllowedAuthenticators(BIOMETRIC_WEAK or DEVICE_CREDENTIAL)
                .setConfirmationRequired(false)
                .build(),
        )
    }
}
