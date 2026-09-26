package com.dincr.app

import android.content.Context
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.ui.RootScreen
import com.dincr.data.MoneyFormat
import com.dincr.design.DincrTheme

class MainActivity : ComponentActivity() {
    private val model: AppModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        enableEdgeToEdge()
        super.onCreate(savedInstanceState)
        model.configure(AppEnvironment.from(intent))
        handleAuthCallback(intent)
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

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleAuthCallback(intent)
    }

    /** Only the OAuth return on our redirect is handled; the code is exchanged with our PKCE verifier. */
    private fun handleAuthCallback(intent: Intent?) {
        val data = intent?.dataString ?: return
        if (data.startsWith(AppEnvironment.AUTH_REDIRECT)) model.handleCallback(data)
    }
}

enum class Appearance {
    SYSTEM, LIGHT, DARK;
    companion object { fun from(raw: String?) = entries.firstOrNull { it.name == raw } ?: SYSTEM }
}
