package com.dincr.data

/**
 * A screen the system can ask the app to open: a launcher shortcut (long-press the app icon) or,
 * on iOS, an App Shortcut (Shortcuts, Siri, Back Tap). It only opens the screen; the user still
 * saves. The signed-in, unlocked shell is the only place that acts on it (iOS: `QuickAction`).
 */
enum class QuickAction(val route: String, val intentAction: String) {
    /** The movement editor, ready for a new expense. */
    NEW_EXPENSE("new_expense", "com.dincr.app.action.NEW_EXPENSE");

    companion object {
        fun fromRoute(route: String?): QuickAction? = entries.firstOrNull { it.route == route }
        fun fromIntentAction(action: String?): QuickAction? = entries.firstOrNull { it.intentAction == action }
    }
}
