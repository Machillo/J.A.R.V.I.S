package com.dincr.data

import java.net.URI

/**
 * Decides how the prototype starts. Same rules as iOS `LaunchPolicy`:
 *
 * - Fixture (sample) data only in a debug build, and only when asked for explicitly (a UI-test
 *   launch extra or the developer's `dincr.fixtures=true`). A release build never runs on
 *   fixtures, whatever it is launched with.
 * - Otherwise the backend must be configured completely, over HTTPS. A debug build may use plain
 *   HTTP on the developer's own machine (loopback or the emulator's host alias) only.
 * - Anything else is [Decision.Unconfigured]: the app says so and stops. It never falls back to
 *   fixtures silently, so sample figures can never be mistaken for a real account.
 */
object LaunchPolicy {
    sealed interface Decision {
        data class Live(val apiUrl: String, val supabaseUrl: String, val anonKey: String) : Decision
        data class Fixtures(val scenario: String?) : Decision
        data class Unconfigured(val reason: Reason) : Decision
    }

    enum class Reason { MISSING, INSECURE_URL, INVALID_URL }

    private val DEV_HOSTS = setOf("localhost", "127.0.0.1", "10.0.2.2", "[::1]", "::1")

    fun decide(
        debugBuild: Boolean,
        launchFixtures: String?,
        fixturesOptIn: Boolean,
        apiUrl: String?,
        supabaseUrl: String?,
        anonKey: String?,
    ): Decision {
        if (debugBuild && (launchFixtures != null || fixturesOptIn)) return Decision.Fixtures(launchFixtures)
        val api = apiUrl?.trim().orEmpty()
        val supabase = supabaseUrl?.trim().orEmpty()
        val key = anonKey?.trim().orEmpty()
        if (api.isEmpty() || supabase.isEmpty() || key.isEmpty()) return Decision.Unconfigured(Reason.MISSING)
        for (url in listOf(api, supabase)) {
            val uri = runCatching { URI(url) }.getOrNull()
            if (uri?.host.isNullOrEmpty() || uri?.rawUserInfo != null || !uri?.rawQuery.isNullOrEmpty() || !uri?.rawFragment.isNullOrEmpty()) {
                return Decision.Unconfigured(Reason.INVALID_URL)
            }
            val scheme = uri!!.scheme?.lowercase()
            val secure = scheme == "https" || (debugBuild && scheme == "http" && uri.host.lowercase() in DEV_HOSTS)
            if (!secure) return Decision.Unconfigured(Reason.INSECURE_URL)
        }
        return Decision.Live(api, supabase, key)
    }
}
