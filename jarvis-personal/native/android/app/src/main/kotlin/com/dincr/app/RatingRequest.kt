package com.dincr.app

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import com.dincr.data.RatingPrompt
import com.google.android.play.core.review.ReviewManagerFactory

/**
 * Counts saved movements on this device and, when [RatingPrompt] says so, asks Google Play for its
 * own rating dialog. Nothing leaves the phone. Fixtures and the Owner are never asked.
 */
object RatingRequest {
    private const val PREFS = "dincr.rating"
    private const val FIRST_OPEN = "firstOpen"
    private const val SAVES = "saves"
    private const val LAST_ASKED = "lastAsked"

    fun movementSaved(context: Context, model: AppModel) {
        if (model.isFixtures || model.profile.value?.role == "owner") return
        val activity = context.findActivity() ?: return
        val prefs = activity.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val now = System.currentTimeMillis()
        val firstOpen = prefs.getLong(FIRST_OPEN, now)
        val saves = prefs.getInt(SAVES, 0) + 1
        prefs.edit().putLong(FIRST_OPEN, firstOpen).putInt(SAVES, saves).apply()
        val lastAsked = prefs.getLong(LAST_ASKED, -1L).takeIf { it >= 0 }
        if (!RatingPrompt.shouldAsk(firstOpen, saves, lastAsked, now)) return
        prefs.edit().putLong(LAST_ASKED, now).apply()
        val manager = ReviewManagerFactory.create(activity)
        manager.requestReviewFlow().addOnSuccessListener { info -> manager.launchReviewFlow(activity, info) }
    }

    private fun Context.findActivity(): Activity? = when (this) {
        is Activity -> this
        is ContextWrapper -> baseContext.findActivity()
        else -> null
    }
}
