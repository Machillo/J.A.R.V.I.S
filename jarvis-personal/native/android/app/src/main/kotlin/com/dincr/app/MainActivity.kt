package com.dincr.app

import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.DefaultLifecycleObserver
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.ProcessLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.ui.RootScreen
import com.dincr.data.MoneyFormat
import com.dincr.design.DincrTheme

/**
 * The single activity. A FragmentActivity because the system biometric prompt needs one. It
 * forwards the sign-in return and the mail-connection return to [AppModel], and tells it when the
 * whole app goes to the background or comes back (app lock, release policy, flags, identity).
 */
class MainActivity : FragmentActivity() {
    private val model: AppModel by viewModels()

    private val processObserver = object : DefaultLifecycleObserver {
        override fun onStart(owner: LifecycleOwner) = model.onForeground()
        override fun onStop(owner: LifecycleOwner) = model.onBackground()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        model.configure(AppEnvironment.from(intent))
        // A recreated activity re-delivers its launch intent: only a fresh launch handles it.
        if (savedInstanceState == null) handleIntent(intent)
        ProcessLifecycleOwner.get().lifecycle.addObserver(processObserver)
        val prefs = getSharedPreferences("dincr.preferences", Context.MODE_PRIVATE)
        var appearance by mutableStateOf(Appearance.from(prefs.getString("appearance", null)))
        setContent {
            val profile by model.profile.collectAsStateWithLifecycle()
            val dark = when (appearance) {
                Appearance.SYSTEM -> isSystemInDarkTheme()
                Appearance.LIGHT -> false
                Appearance.DARK -> true
            }
            DincrTheme(darkTheme = dark, moneyFormat = MoneyFormat.from(profile)) {
                RootScreen(model, appearance) { next ->
                    appearance = next
                    prefs.edit().putString("appearance", next.name).apply()
                }
            }
        }
    }

    override fun onDestroy() {
        ProcessLifecycleOwner.get().lifecycle.removeObserver(processObserver)
        super.onDestroy()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleIntent(intent)
    }

    /**
     * The sign-in return is accepted only as our exact redirect with a code while a sign-in we
     * started is pending; a mail return only as `<scheme>://gmail/callback`, redeemed once.
     */
    private fun handleIntent(intent: Intent?) {
        val data = intent?.dataString ?: return
        when (intent.action) {
            MailReturnActivity.ACTION_MAIL_RETURN -> model.handleMailReturn(data)
            Intent.ACTION_VIEW -> model.handleCallback(data)
        }
    }
}

enum class Appearance {
    SYSTEM, LIGHT, DARK;
    companion object { fun from(raw: String?) = entries.firstOrNull { it.name == raw } ?: SYSTEM }
}
