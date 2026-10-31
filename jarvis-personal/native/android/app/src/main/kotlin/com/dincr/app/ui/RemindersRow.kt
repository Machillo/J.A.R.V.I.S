package com.dincr.app.ui

import android.Manifest
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Notifications
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp
import com.dincr.app.AppModel
import com.dincr.app.ReminderScheduler
import com.dincr.app.tx
import com.dincr.design.Dincr
import com.dincr.design.generated.DincrSpacing
import kotlinx.coroutines.launch

/** NT-1 — Perfil → Recordatorios: turns the reminders on the phone on (asking the permission) or off. iOS: `ProfileHubView`. */
@Composable
fun RemindersRow(model: AppModel) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var on by remember { mutableStateOf(ReminderScheduler.isEnabled(context) && ReminderScheduler.hasPermission(context)) }
    var denied by remember { mutableStateOf(false) }
    fun turnOn() {
        ReminderScheduler.setEnabled(context, true); on = true; denied = false
        scope.launch { ReminderScheduler.refresh(context, model) }
    }
    val permission = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
        if (granted) turnOn() else { ReminderScheduler.setEnabled(context, false); on = false; denied = true }
    }
    Row(Modifier.heightIn(min = 56.dp).padding(vertical = DincrSpacing.s2).testTag("profile.reminders"), verticalAlignment = Alignment.CenterVertically) {
        Icon(Icons.Rounded.Notifications, contentDescription = null, tint = Dincr.colors.tint)
        Column(Modifier.weight(1f).padding(horizontal = DincrSpacing.s3)) {
            Text(tx("Recordatorios", "Reminders"), style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text)
            Text(if (denied) tx("Permitilas en Ajustes › Apps › DINCR › Notificaciones.", "Allow them in Settings › Apps › DINCR › Notifications.")
                else tx("Cuotas, gastos fijos, Salvavidas y fin de mes", "Payments, fixed expenses, emergency fund and month end"),
                style = MaterialTheme.typography.bodySmall, color = Dincr.colors.text2)
        }
        Switch(checked = on, onCheckedChange = { wanted ->
            when {
                !wanted -> { ReminderScheduler.setEnabled(context, false); on = false }
                ReminderScheduler.hasPermission(context) -> turnOn()
                Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU -> permission.launch(Manifest.permission.POST_NOTIFICATIONS)
                else -> turnOn()
            }
        })
    }
}
