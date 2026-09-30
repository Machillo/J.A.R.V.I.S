package com.dincr.data

/**
 * JARVIS: the Owner's personal capabilities inside DINCR (JARVIS recovery roadmap, step J0).
 *
 * DINCR has four kinds of account: Free, Basic and VIP (plans) and the single Owner (a server role,
 * never a plan). The Owner uses the public app at VIP level (#296) and, on top of it, JARVIS.
 * - Only the role in `/auth/me` opens it: never a plan code, a stored flag or a local copy of the
 *   profile. The app only shows or hides the entry; the backend decides every JARVIS request.
 * - Admin is not the Owner and never gets JARVIS.
 *
 * iOS twin: `Jarvis.swift`.
 */
object Jarvis {
    /** Whether the app offers JARVIS to this identity. */
    fun isAvailable(profile: Profile?): Boolean = profile?.isOwner == true

    /**
     * The personal capabilities JARVIS brings back, in the recovery roadmap's order. A section not
     * ported yet opens a "being restored" screen; the step that ports it makes it available here,
     * with its own tests.
     */
    enum class Section(val wire: String) {
        CHAT("chat"), MEMORY("memory"), CALENDAR("calendar"), STRATEGY("strategy"), MONEY("money"),
        MONEY_CONTROL("money_control"), WEALTH("wealth"), RECORDS("records");

        /** Ported to the native app: the chat (J1); the others still open "being restored". */
        val isAvailable: Boolean get() = this == CHAT

        companion object {
            fun from(wire: String?): Section? = entries.firstOrNull { it.wire == wire }
        }
    }
}
