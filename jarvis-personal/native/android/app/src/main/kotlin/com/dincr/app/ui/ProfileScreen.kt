package com.dincr.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Construction
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.AppModel
import com.dincr.app.Appearance
import com.dincr.app.tx
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.EmptyState
import com.dincr.design.generated.DincrRadius
import com.dincr.design.generated.DincrSpacing

@Composable
fun ProfileScreen(model: AppModel, padding: PaddingValues, appearance: Appearance, onAppearance: (Appearance) -> Unit) {
    val profile by model.profile.collectAsStateWithLifecycle()
    var confirming by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(DincrSpacing.s4), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s4), horizontalAlignment = Alignment.CenterHorizontally) {
        Text(tx("Perfil", "Profile"), style = MaterialTheme.typography.headlineMedium, color = Dincr.colors.text, modifier = Modifier.widthIn(max = 600.dp).fillMaxWidth().padding(top = DincrSpacing.s6).semantics { heading() })
        Column(Modifier.widthIn(max = 600.dp)) {
            DincrCard {
                Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.semantics(mergeDescendants = true) {}) {
                    Box(Modifier.size(44.dp).background(Dincr.colors.tintContainer, CircleShape), contentAlignment = Alignment.Center) {
                        Text(profile?.firstName?.take(1) ?: "D", color = Dincr.colors.onTintContainer, style = MaterialTheme.typography.titleMedium)
                    }
                    Column(Modifier.weight(1f).padding(horizontal = DincrSpacing.s3)) {
                        Text(profile?.displayName ?: tx("Tu cuenta", "Your account"), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
                        Text(profile?.email.orEmpty(), style = MaterialTheme.typography.bodySmall, color = Dincr.colors.textMuted)
                    }
                    PlanBadge(profile?.plan ?: "free")
                }
            }
        }
        Column(Modifier.widthIn(max = 600.dp).fillMaxWidth().background(Dincr.colors.surface, RoundedCornerShape(DincrRadius.lg)).padding(vertical = DincrSpacing.s2)) {
            Text(tx("Apariencia", "Appearance"), style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2, modifier = Modifier.padding(horizontal = DincrSpacing.s4, vertical = DincrSpacing.s2))
            listOf(Appearance.SYSTEM to tx("Automático", "Automatic"), Appearance.LIGHT to tx("Claro", "Light"), Appearance.DARK to tx("Oscuro", "Dark")).forEach { (value, label) ->
                Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).selectable(appearance == value, role = Role.RadioButton) { onAppearance(value) }.padding(horizontal = DincrSpacing.s2), verticalAlignment = Alignment.CenterVertically) {
                    RadioButton(appearance == value, null)
                    Text(label, color = Dincr.colors.text, modifier = Modifier.padding(start = DincrSpacing.s2))
                }
            }
        }
        TextButton({ confirming = true }, Modifier.widthIn(max = 600.dp).fillMaxWidth().heightIn(min = 48.dp)) {
            Text(tx("Cerrar sesión", "Sign out"), color = Dincr.colors.negative, style = MaterialTheme.typography.titleMedium)
        }
    }
    if (confirming) AlertDialog(
        onDismissRequest = { confirming = false },
        title = { Text(tx("¿Cerrar sesión en este dispositivo?", "Sign out on this device?")) },
        confirmButton = { TextButton({ confirming = false; model.signOut() }) { Text(tx("Cerrar sesión", "Sign out"), color = Dincr.colors.negative) } },
        dismissButton = { TextButton({ confirming = false }) { Text(tx("Cancelar", "Cancel")) } },
    )
}

/** Display name of a backend plan code. The plan itself always comes from `/auth/me`. */
fun planName(plan: String?): String = when (plan ?: "free") {
    "free" -> tx("Gratis", "Free")
    "vip" -> "VIP"
    else -> (plan ?: "").replaceFirstChar { it.uppercase() }
}

@Composable
fun PlanBadge(plan: String) {
    val vip = plan == "vip"
    Text(planName(plan),
        style = MaterialTheme.typography.labelMedium, color = if (vip) Dincr.colors.vip else Dincr.colors.text2,
        modifier = Modifier.background(if (vip) Dincr.colors.vipContainer else Dincr.colors.surface2, CircleShape).padding(horizontal = 8.dp, vertical = 2.dp))
}

@Composable
fun PlaceholderScreen(title: String, parity: String, padding: PaddingValues) {
    Column(Modifier.fillMaxSize().padding(padding).padding(DincrSpacing.s4), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(DincrSpacing.s4)) {
        Text(title, style = MaterialTheme.typography.headlineMedium, color = Dincr.colors.text, modifier = Modifier.widthIn(max = 600.dp).fillMaxWidth().padding(top = DincrSpacing.s6).semantics { heading() })
        Column(Modifier.widthIn(max = 600.dp)) {
            EmptyState(Icons.Rounded.Construction, tx("En construcción", "Under construction"),
                tx("Esta sección llega en los módulos siguientes de la app nativa ($parity). Mientras tanto, usala desde la app actual de DINCR.", "This section arrives in the next native modules ($parity). Meanwhile, use it in the current DINCR app."))
        }
    }
}
