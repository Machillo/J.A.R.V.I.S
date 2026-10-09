package com.dincr.data

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.async

/**
 * B17 — pull to refresh on Plan, Patrimonio and Perfil (Hoy and Movimientos keep their own). A tab
 * reads again only what it already reads: the identity (plan and role, `/auth/me`), the operational
 * switches and, in Patrimonio, the debts. A failed refresh never empties a screen: it keeps what it
 * showed and says so apart ([failureNotice]). iOS: `PullRefresh`.
 */
object PullRefresh {
    /**
     * What a screen shows after a refresh: the new answer, or what it already showed when the
     * refresh failed. Null only when there was nothing to keep (the screen shows its own error).
     */
    fun <T> kept(current: T?, result: Result<T>): T? = result.getOrElse { current }

    fun failureNotice(language: AppLanguage = AppLanguage.current()): String =
        language.pick("No pudimos actualizar. Seguís viendo la información anterior.",
            "We couldn’t refresh. You’re still seeing the previous information.")
}

/**
 * One refresh at a time: a refresh asked for while another is running (a second pull, here or on
 * another tab) waits for that one and gets its result instead of asking again. The
 * work runs in [scope] (the model's), so leaving the tab never cuts it in half. Used from the main
 * thread only. iOS: `SingleFlight`.
 */
class SingleFlight(private val scope: CoroutineScope) {
    private var running: Deferred<Boolean>? = null

    val isRunning: Boolean get() = running?.isActive == true

    suspend fun run(work: suspend () -> Boolean): Boolean {
        running?.takeIf { it.isActive }?.let { return it.await() }
        val task = scope.async { work() }
        running = task
        return try { task.await() } finally { if (running === task) running = null }
    }
}
