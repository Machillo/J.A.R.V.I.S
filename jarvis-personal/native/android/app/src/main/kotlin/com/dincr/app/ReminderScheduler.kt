package com.dincr.app

import android.Manifest
import android.app.AlarmManager
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat
import com.dincr.data.Jarvis
import com.dincr.data.PlanTier
import com.dincr.data.Reminders
import java.time.LocalDate
import java.time.ZoneId

/**
 * NT-1 — the reminders on the phone (local notifications; no server, no token). Turned on in
 * Perfil → Recordatorios, which asks the system permission (Android 13+). When the app is ready and
 * every time it comes back, it reads the debts, the fixed expenses and the Salvavidas plan, asks
 * [Reminders.plan] which reminders the next weeks need, and replaces the alarms it set before. A failed
 * read keeps the alarms already set; signing out cancels them. The alarm posts the notification
 * ([ReminderReceiver]). iOS twin: `ReminderScheduler.swift`.
 */
object ReminderScheduler {
    private const val PREFS = "dincr.reminders"
    private const val KEY_ON = "on"
    private const val KEY_IDS = "ids"
    const val CHANNEL = "reminders"

    fun isEnabled(context: Context) = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean(KEY_ON, false)

    fun setEnabled(context: Context, on: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putBoolean(KEY_ON, on).apply()
        if (!on) clear(context)
    }

    fun hasPermission(context: Context) = Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU ||
        ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED

    suspend fun refresh(context: Context, model: AppModel) {
        if (!isEnabled(context) || !hasPermission(context) || model.isFixtures) return
        val profile = model.profile.value ?: return
        val bills = runCatching {
            val fixed = if (profile.planTier != PlanTier.VIP) emptyList()
            else if (Jarvis.isAvailable(profile)) model.api.ownerFixedExpenses().mapNotNull { item ->
                item.dueDay?.let { Reminders.Bill("fixed-${item.id}", Reminders.Bill.Kind.FIXED, item.name.orEmpty(), item.expectedAmount, it) }
            } else model.api.recurring().items.mapNotNull { item ->
                val day = item.dueDay
                if (item.itemType != "expense" || item.isActive == false || (item.frequency ?: "monthly") != "monthly" || day == null) null
                else Reminders.Bill("fixed-${item.id}", Reminders.Bill.Kind.FIXED, item.name.orEmpty(), item.amount, day)
            }
            Reminders.bills(model.api.debts(), fixed)
        }.getOrElse { return }
        val saving = if (profile.planTier == PlanTier.VIP) runCatching { model.api.salvavidas().autoContribution }.getOrNull() else null
        // DB-1: the day each of the Owner's locked savings blocks matures.
        val blocks = if (Jarvis.isAvailable(profile)) runCatching { model.api.debtSavingsBlocks().blocks.orEmpty() }.getOrDefault(emptyList()) else emptyList()
        // The days the bank says what it did with an extra payment.
        val waiting = runCatching {
            val pending = model.api.debtsAfterExtraPending()
            model.api.debts().mapNotNull { debt -> pending[debt.id.toString()]?.remindOn?.let { Triple(debt.id, debt.name.orEmpty(), it) } }
        }.getOrDefault(emptyList())
        schedule(context, Reminders.plan(LocalDate.now(), bills, saving, model.moneyFormat, blocks = blocks, waiting = waiting))
    }

    private fun schedule(context: Context, plan: List<Reminders.Reminder>) {
        clear(context)
        val alarms = context.getSystemService(AlarmManager::class.java) ?: return
        val zone = ZoneId.systemDefault()
        plan.forEach { reminder ->
            val at = reminder.at.atZone(zone).toInstant().toEpochMilli()
            alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, at, pending(context, reminder.id, reminder.title, reminder.body))
        }
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().putStringSet(KEY_IDS, plan.map { it.id }.toSet()).apply()
    }

    fun clear(context: Context) {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val alarms = context.getSystemService(AlarmManager::class.java)
        prefs.getStringSet(KEY_IDS, emptySet()).orEmpty().forEach { id -> alarms?.cancel(pending(context, id, "", "")) }
        prefs.edit().remove(KEY_IDS).apply()
    }

    private fun pending(context: Context, id: String, title: String, body: String): PendingIntent =
        PendingIntent.getBroadcast(context, id.hashCode(),
            Intent(context, ReminderReceiver::class.java).setAction(id).putExtra("title", title).putExtra("body", body),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
}

/** Posts a scheduled reminder; tapping it opens DINCR. */
class ReminderReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (!ReminderScheduler.hasPermission(context) || !ReminderScheduler.isEnabled(context)) return
        val manager = context.getSystemService(NotificationManager::class.java) ?: return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(NotificationChannel(ReminderScheduler.CHANNEL, tx("Recordatorios", "Reminders"), NotificationManager.IMPORTANCE_DEFAULT))
        }
        val open = PendingIntent.getActivity(context, 0, Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notification = NotificationCompat.Builder(context, ReminderScheduler.CHANNEL)
            .setSmallIcon(android.R.drawable.ic_popup_reminder)
            .setContentTitle(intent.getStringExtra("title"))
            .setContentText(intent.getStringExtra("body"))
            .setStyle(NotificationCompat.BigTextStyle().bigText(intent.getStringExtra("body")))
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) return
        NotificationManagerCompat.from(context).notify(intent.action.hashCode(), notification)
    }
}
