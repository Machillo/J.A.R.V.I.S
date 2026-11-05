package com.dincr.app

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Test

class ReminderBootTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()
    private val prefs get() = context.getSharedPreferences("dincr.reminders", Context.MODE_PRIVATE)

    @After fun clean() { prefs.edit().clear().commit() }

    @Test fun aRestartSetsOnlyTheFutureRemindersAgain() {
        prefs.edit().putBoolean("on", true).putStringSet("at", setOf("1000|past", "5000|future", "6000|later", "bad|x")).commit()
        assertEquals(2, ReminderScheduler.restoreAfterBoot(context, now = 2000))
    }

    @Test fun remindersOffSetNothing() {
        prefs.edit().putBoolean("on", false).putStringSet("at", setOf("5000|future")).commit()
        assertEquals(0, ReminderScheduler.restoreAfterBoot(context, now = 2000))
    }
}
