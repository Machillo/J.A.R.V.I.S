package com.dincr.app

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.content.Intent
import android.os.Build
import android.service.quicksettings.TileService
import android.widget.RemoteViews
import com.dincr.data.QuickAction

/**
 * Faster ways to the editor of a new expense, like iOS's shortcut: a quick settings tile and a home
 * screen widget. They only open the app, which asks for its lock and session as usual: they read
 * nothing and record nothing, and need no permission.
 */
private fun newExpenseIntent(context: Context): Intent =
    Intent(context, MainActivity::class.java).setAction(QuickAction.NEW_EXPENSE.intentAction).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP)

private fun newExpensePendingIntent(context: Context): PendingIntent =
    PendingIntent.getActivity(context, 0, newExpenseIntent(context), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)

class QuickExpenseTile : TileService() {
    override fun onClick() {
        super.onClick()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startActivityAndCollapse(newExpensePendingIntent(this))
        } else {
            @Suppress("DEPRECATION", "StartActivityAndCollapseDeprecated")
            startActivityAndCollapse(newExpenseIntent(this))
        }
    }
}

class QuickExpenseWidget : AppWidgetProvider() {
    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        val views = RemoteViews(context.packageName, R.layout.widget_quick_expense)
        views.setOnClickPendingIntent(R.id.widget_quick_expense, newExpensePendingIntent(context))
        ids.forEach { manager.updateAppWidget(it, views) }
    }
}
