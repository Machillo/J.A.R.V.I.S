package com.dincr.app.ui

import androidx.compose.animation.Crossfade
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.HourglassTop
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.AppModel
import com.dincr.app.Appearance
import com.dincr.app.Phase
import com.dincr.app.tx
import com.dincr.design.Dincr
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.generated.DincrSpacing

@Composable
fun RootScreen(model: AppModel, appearance: Appearance, onAppearance: (Appearance) -> Unit) {
    val phase by model.phase.collectAsStateWithLifecycle()
    Box(Modifier.fillMaxSize().background(Dincr.colors.bg)) {
        Crossfade(targetState = phase, label = "phase") { current ->
            when (current) {
                Phase.Booting, Phase.LoadingIdentity -> BootScreen()
                Phase.SignedOut -> LoginScreen(model)
                is Phase.IdentityError -> GateScreen(Icons.Rounded.Warning, tx("No pudimos cargar tu cuenta", "We couldn’t load your account"), current.message,
                    primary = tx("Intentar de nuevo", "Try again") to { model.retryIdentity() }, onSignOut = { model.signOut() })
                // Owner boundary (CLAUDE.md §4.A): the public app never renders Owner features.
                Phase.OwnerNotSupported -> GateScreen(Icons.Rounded.Lock, tx("Esta cuenta usa DINCR Owner", "This account uses DINCR Owner"),
                    tx("La app pública de DINCR no muestra funciones internas. Cerrá sesión para entrar con otra cuenta.", "The public DINCR app doesn’t show internal features. Sign out to use another account."),
                    primary = null, onSignOut = { model.signOut() })
                is Phase.NotYetSupported -> GateScreen(Icons.Rounded.HourglassTop, tx("Un paso más", "One more step"), current.message, primary = null, onSignOut = { model.signOut() })
                Phase.ProfileSetup -> ProfileSetupScreen(model)
                Phase.Ready -> MainScaffold(model, appearance, onAppearance)
            }
        }
    }
}

@Composable
fun BrandMark(size: Int = 48) {
    Box(Modifier.size(size.dp).background(Dincr.colors.tint, RoundedCornerShape((size * 0.28f).dp)), contentAlignment = Alignment.Center) {
        Text("D", color = Dincr.colors.onTint, fontWeight = FontWeight.Black, fontSize = (size * 0.5f).sp)
    }
}

@Composable
private fun BootScreen() {
    val label = tx("Preparando tu espacio", "Preparing your space")
    Column(Modifier.fillMaxSize().semantics(mergeDescendants = true) { contentDescription = label }, verticalArrangement = Arrangement.Center, horizontalAlignment = Alignment.CenterHorizontally) {
        BrandMark(56)
        CircularProgressIndicator(Modifier.padding(top = DincrSpacing.s4).size(24.dp), color = Dincr.colors.tint, strokeWidth = 2.dp)
    }
}

@Composable
private fun GateScreen(icon: ImageVector, title: String, message: String, primary: Pair<String, () -> Unit>?, onSignOut: () -> Unit) {
    Column(
        Modifier.fillMaxSize().safeDrawingPadding().padding(DincrSpacing.s6),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(DincrSpacing.s4),
    ) {
        Spacer(Modifier.weight(1f))
        Icon(icon, contentDescription = null, tint = Dincr.colors.tint, modifier = Modifier.size(40.dp))
        Text(title, style = MaterialTheme.typography.headlineSmall, color = Dincr.colors.text, textAlign = TextAlign.Center)
        Text(message, style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text2, textAlign = TextAlign.Center, modifier = Modifier.widthIn(max = 560.dp))
        Spacer(Modifier.weight(1f))
        primary?.let { (label, action) -> DincrPrimaryButton(label, action, Modifier.widthIn(max = 560.dp)) }
        TextButton(onClick = onSignOut, modifier = Modifier.heightIn(min = 48.dp)) {
            Text(tx("Cerrar sesión", "Sign out"), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.tint)
        }
    }
}
