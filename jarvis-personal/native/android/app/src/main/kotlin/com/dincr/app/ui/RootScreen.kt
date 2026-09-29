package com.dincr.app.ui

import android.content.Intent
import android.net.Uri
import androidx.compose.animation.Crossfade
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Lock
import androidx.compose.material.icons.rounded.SystemUpdate
import androidx.compose.material.icons.rounded.Warning
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
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
import com.dincr.data.AppLanguage
import com.dincr.data.LaunchPolicy
import com.dincr.data.ReleasePolicy
import com.dincr.design.Dincr
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.generated.DincrSpacing
import kotlinx.coroutines.launch

@Composable
fun RootScreen(model: AppModel, appearance: Appearance, onAppearance: (Appearance) -> Unit) {
    val phase by model.phase.collectAsStateWithLifecycle()
    val locked by model.appLock.locked.collectAsStateWithLifecycle()
    Box(Modifier.fillMaxSize().background(Dincr.colors.bg)) {
        Crossfade(targetState = phase, label = "phase") { current ->
            when (current) {
                Phase.Booting, Phase.LoadingIdentity -> BootScreen()
                // No backend: say so and stop. There is no session to close and no sample data.
                is Phase.Unconfigured -> GateScreen(Icons.Rounded.Warning, tx("App sin servidor configurado", "App without a configured server"),
                    when (current.reason) {
                        LaunchPolicy.Reason.MISSING -> tx("Esta compilación no tiene la dirección del servidor ni la de inicio de sesión. Configurala en local.properties (native/README.md).", "This build has no server or sign-in address. Set them in local.properties (native/README.md).")
                        LaunchPolicy.Reason.INSECURE_URL -> tx("Las direcciones del servidor deben usar HTTPS.", "Server addresses must use HTTPS.")
                        LaunchPolicy.Reason.INVALID_URL -> tx("Una dirección del servidor no es válida.", "A server address is not valid.")
                    },
                    primary = null, onSignOut = null)
                Phase.SignedOut -> LoginScreen(model)
                is Phase.IdentityError -> IdentityErrorScreen(model, current)
                is Phase.UpdateRequired -> UpdateRequiredScreen(model, current.policy)
                // Owner boundary (CLAUDE.md §4.A): the public app never renders Owner features.
                Phase.OwnerNotSupported -> GateScreen(Icons.Rounded.Lock, tx("Esta cuenta usa DINCR Owner", "This account uses DINCR Owner"),
                    tx("La app pública de DINCR no muestra funciones internas. Cerrá sesión para entrar con otra cuenta.", "The public DINCR app doesn’t show internal features. Sign out to use another account."),
                    primary = null, onSignOut = { model.signOut() })
                Phase.LegalRequired -> LegalConsentScreen(model)
                Phase.ProfileSetup -> ProfileSetupScreen(model)
                Phase.ChoosePlan -> PlanChooserScreen(model)
                // The lock replaces the app instead of covering it: sheets and dialogs are windows
                // of their own and would stay visible and usable above an overlay.
                Phase.Ready -> if (locked) LockScreen(model) else MainScaffold(model, appearance, onAppearance)
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
fun GateScreen(icon: ImageVector, title: String, message: String, primary: Pair<String, () -> Unit>?, onSignOut: (() -> Unit)?, secondary: Pair<String, () -> Unit>? = null, busy: Boolean = false) {
    Column(
        Modifier.fillMaxSize().safeDrawingPadding().padding(DincrSpacing.s6),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(DincrSpacing.s4),
    ) {
        Spacer(Modifier.weight(1f))
        Icon(icon, contentDescription = null, tint = Dincr.colors.tint, modifier = Modifier.size(40.dp))
        Text(title, style = MaterialTheme.typography.headlineSmall, color = Dincr.colors.text, textAlign = TextAlign.Center)
        Text(message, style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text2, textAlign = TextAlign.Center, modifier = Modifier.widthIn(max = 560.dp))
        Spacer(Modifier.weight(1f))
        primary?.let { (label, action) -> DincrPrimaryButton(label, action, Modifier.widthIn(max = 560.dp), loading = busy) }
        secondary?.let { (label, action) ->
            TextButton(onClick = action, enabled = !busy, modifier = Modifier.heightIn(min = 48.dp)) { Text(label, style = MaterialTheme.typography.titleMedium, color = Dincr.colors.tint) }
        }
        onSignOut?.let { signOut ->
            TextButton(onClick = signOut, enabled = !busy, modifier = Modifier.heightIn(min = 48.dp)) {
                Text(tx("Cerrar sesión", "Sign out"), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.tint)
            }
        }
    }
}

/** `/auth/me` failed: retry or sign out; finish a pending deletion when that is the cause. */
@Composable
private fun IdentityErrorScreen(model: AppModel, state: Phase.IdentityError) {
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    var message by remember(state) { mutableStateOf(state.message) }
    if (state.deletionPending) {
        GateScreen(Icons.Rounded.Warning, tx("Tu cuenta se está eliminando", "Your account is being deleted"), message,
            primary = tx("Terminar eliminación", "Finish deletion") to {
                busy = true
                scope.launch { model.deleteAccount()?.let { message = it }; busy = false }
                Unit
            }, onSignOut = { model.signOut() }, busy = busy)
    } else {
        GateScreen(Icons.Rounded.Warning, tx("No pudimos cargar tu cuenta", "We couldn’t load your account"), message,
            primary = tx("Intentar de nuevo", "Try again") to { model.retryIdentity(); Unit }, onSignOut = { model.signOut() })
    }
}

/** The release policy requires a newer version: update or check again (never a dead end). */
@Composable
private fun UpdateRequiredScreen(model: AppModel, policy: ReleasePolicy) {
    val context = LocalContext.current
    GateScreen(Icons.Rounded.SystemUpdate, tx("Actualizá DINCR", "Update DINCR"),
        (if (AppLanguage.current() == AppLanguage.SPANISH) policy.messageEs else policy.messageEn)
            ?: tx("Esta versión ya no es compatible. Instalá la versión más reciente para seguir.", "This version is no longer supported. Install the latest version to continue."),
        primary = policy.updateUrl?.takeIf { it.startsWith("https://") }?.let { url ->
            tx("Actualizar", "Update") to { runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }; Unit }
        },
        secondary = tx("Comprobar nuevamente", "Check again") to { model.recheckRelease(); Unit },
        onSignOut = null)
}
