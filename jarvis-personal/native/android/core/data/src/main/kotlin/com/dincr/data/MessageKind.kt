package com.dincr.data

/**
 * What a message on screen means (DESIGN.md → Messages). Each kind looks different, so the user
 * recognises it before reading: a technical problem in DINCR never looks like a financial
 * situation, and a financial situation never looks like a failure of the app.
 * iOS has the same mapping in `DincrCore.MessageKind`.
 */
enum class MessageKind {
    /** Something in DINCR failed or is degraded: network, service, a connection that must be redone. */
    TECHNICAL_ERROR,
    /** A financial situation worth the user's attention. */
    ATTENTION,
    /** Something DINCR found that could help: a recommendation. */
    OPPORTUNITY,
    /** Progress, an improvement or a reached milestone. */
    POSITIVE;

    companion object {
        /**
         * The kind of a financial alert from the severity the backend sends to the alert screens
         * (`critical`, `high`, `medium`, `success`). Only `success` is progress; every other severity,
         * including unknown or missing ones, stays visible as [ATTENTION]: a problem is never
         * downplayed to a suggestion, and a financial alert is never a technical error. No backend
         * severity means "opportunity" today; recommendations get that kind explicitly.
         */
        fun financial(severity: String?): MessageKind = if (severity?.lowercase() == "success") POSITIVE else ATTENTION
    }
}
