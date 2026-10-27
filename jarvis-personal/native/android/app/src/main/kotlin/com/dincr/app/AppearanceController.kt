package com.dincr.app

import android.content.SharedPreferences
import com.dincr.data.AppearancePolicy
import com.dincr.data.AppearancePrefs
import com.dincr.data.AppearanceState
import com.dincr.data.CachedAppearance
import com.dincr.data.DincrApi
import com.dincr.data.Profile
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.launch

/**
 * APP-1 — the personal appearance of the signed-in account (phase 1: the Owner only).
 *
 * The server keeps it per account (`/user-product/appearance`), so it follows the Owner to every
 * device; this device keeps the last one the same account saved, so the app opens in that look
 * before the network answers. [effective] is what the theme draws: [AppearancePolicy] gives every
 * other account the classic look, whatever is stored. While the Personalización screen is open, its
 * draft is drawn instead ([preview]), so every change shows at once across the app; leaving the
 * screen clears it. iOS: not yet (MAC REQUIRED, APP-1 phase 1 notes).
 */
class AppearanceController(private val store: SharedPreferences, scope: CoroutineScope, private val api: () -> DincrApi) {
    private val launcher = scope
    private val profile = MutableStateFlow<Profile?>(null)
    private val saved = MutableStateFlow<AppearanceState?>(null)
    private val draft = MutableStateFlow<AppearancePrefs?>(null)
    private val cached = MutableStateFlow(CachedAppearance.decode(store.getString(CACHE_KEY, null)))

    /** The server's answer for this account, once read. */
    val state: StateFlow<AppearanceState?> = saved.asStateFlow()

    val effective: StateFlow<AppearancePrefs> = combine(profile, saved, draft, cached) { who, server, preview, local ->
        if (preview != null && AppearancePolicy.isPersonalizable(who)) preview.sanitized()
        else AppearancePolicy.effective(who, server?.preferences, local)
    }.stateIn(scope, SharingStarted.Eagerly, AppearancePrefs.CLASSIC)

    /** A new or refreshed identity. Another account starts clean; the Owner's choice is read again. */
    fun onIdentity(next: Profile) {
        val previous = profile.value
        if (previous?.id != next.id) {
            saved.value = null
            draft.value = null
        }
        profile.value = next
        if (AppearancePolicy.isPersonalizable(next)) launcher.launch { runCatching { load() } }
        else saved.value = null
    }

    /** `GET /user-product/appearance` (the Owner only; the server refuses everyone else). */
    suspend fun load(): AppearanceState = api().appearance().also(::remember)

    suspend fun save(prefs: AppearancePrefs): AppearanceState = api().saveAppearance(prefs).also {
        remember(it)
        draft.value = null
    }

    /** Back to the defaults: the stored choice is removed on the server. */
    suspend fun reset(): AppearanceState = api().resetAppearance().also {
        remember(it)
        draft.value = null
    }

    /** The draft of the Personalización screen, drawn app-wide while it is open; null ends the preview. */
    fun preview(prefs: AppearancePrefs?) {
        draft.value = prefs
    }

    /** Signed out: nothing of this account's appearance stays on the device. */
    fun clear() {
        profile.value = null
        saved.value = null
        draft.value = null
        cached.value = null
        store.edit().remove(CACHE_KEY).apply()
    }

    private fun remember(answer: AppearanceState) {
        val who = profile.value ?: return
        if (!AppearancePolicy.isPersonalizable(who)) return
        saved.value = answer
        val entry = CachedAppearance(who.id, answer.preferences.sanitized())
        cached.value = entry
        store.edit().putString(CACHE_KEY, entry.encode()).apply()
    }

    private companion object {
        const val CACHE_KEY = "personal_appearance"
    }
}
