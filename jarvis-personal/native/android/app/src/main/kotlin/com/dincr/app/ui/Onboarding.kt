package com.dincr.app.ui

import android.net.Uri
import androidx.browser.customtabs.CustomTabsIntent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Check
import androidx.compose.material.icons.rounded.Fingerprint
import androidx.compose.material.icons.rounded.Gavel
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.fragment.app.FragmentActivity
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.AppLock
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AuthException
import com.dincr.data.BillingCatalog
import com.dincr.data.LegalAcceptRequest
import com.dincr.data.PlanChangeRequest
import com.dincr.data.PlanOption
import com.dincr.design.BannerTone
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.ErrorState
import com.dincr.design.StatusBanner
import com.dincr.design.generated.DincrRadius
import com.dincr.design.generated.DincrSpacing
import kotlinx.coroutines.launch

const val TERMS_URL = "https://dincr.com/terminos/"
const val PRIVACY_URL = "https://dincr.com/privacidad/"
/** The backend default for `POST /auth/plan` (auth/models.py). */
const val PLAN_CONSENT_VERSION = "regular-2027-v1"

fun openInBrowser(context: android.content.Context, url: String) {
    runCatching { CustomTabsIntent.Builder().setShowTitle(true).build().launchUrl(context, Uri.parse(url)) }
}

@Composable
private fun OnboardingColumn(content: @Composable () -> Unit) {
    Box(Modifier.fillMaxSize().safeDrawingPadding(), contentAlignment = Alignment.TopCenter) {
        Column(
            Modifier.widthIn(max = ContentMaxWidth).fillMaxWidth().verticalScroll(rememberScrollState()).padding(DincrSpacing.s5),
            verticalArrangement = Arrangement.spacedBy(DincrSpacing.s4),
        ) { content() }
    }
}

/** A8 — terms and privacy must both be accepted (the versions come from `/auth/me.legal`). */
@Composable
fun LegalConsentScreen(model: AppModel) {
    val profile by model.profile.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var terms by remember { mutableStateOf(false) }
    var privacy by remember { mutableStateOf(false) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val legal = profile?.legal
    OnboardingColumn {
        Icon(Icons.Rounded.Gavel, contentDescription = null, tint = Dincr.colors.tint, modifier = Modifier.size(40.dp))
        Text(tx("Antes de seguir", "Before you continue"), style = MaterialTheme.typography.headlineSmall, color = Dincr.colors.text, modifier = Modifier.semantics { heading() })
        Text(tx("Actualizamos los términos y la política de privacidad. Leelos y aceptalos para usar DINCR.", "We updated the terms and the privacy policy. Read and accept them to use DINCR."),
            style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text2)
        ConsentRow(tx("Acepto los Términos y Condiciones", "I accept the Terms and Conditions"), legal?.termsVersion, terms, { terms = it }) { openInBrowser(context, TERMS_URL) }
        ConsentRow(tx("Acepto la Política de Privacidad", "I accept the Privacy Policy"), legal?.privacyVersion, privacy, { privacy = it }) { openInBrowser(context, PRIVACY_URL) }
        error?.let { ErrorState(it) }
        DincrPrimaryButton(tx("Aceptar y continuar", "Accept and continue"), loading = busy, enabled = terms && privacy && legal?.termsVersion != null && legal.privacyVersion != null, onClick = {
            busy = true; error = null
            scope.launch {
                model.load(tx("No pudimos registrar tu aceptación.", "We couldn’t record your acceptance.")) {
                    model.api.acceptLegal(LegalAcceptRequest(true, true, legal!!.termsVersion!!, legal.privacyVersion!!))
                    model.api.me()
                }.onSuccess { model.apply(it) }.onFailure { if (it !is AuthException.SignedOut) error = it.message }
                busy = false
            }
        })
        TextButton({ model.signOut() }, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) { Text(tx("Cerrar sesión", "Sign out"), color = Dincr.colors.tint) }
    }
}

@Composable
private fun ConsentRow(label: String, version: String?, checked: Boolean, onChange: (Boolean) -> Unit, onOpen: () -> Unit) {
    DincrCard {
        Column {
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).toggleable(checked, role = Role.Checkbox, onValueChange = onChange), verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked, onCheckedChange = null)
                Column(Modifier.padding(start = DincrSpacing.s2)) {
                    Text(label, style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text)
                    version?.let { Text(tx("Versión $it", "Version $it"), style = MaterialTheme.typography.bodySmall, color = Dincr.colors.textMuted) }
                }
            }
            TextButton(onOpen, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Leer documento", "Read document"), color = Dincr.colors.tint) }
        }
    }
}

/** A11 — first plan choice. Paid plans are offered only while the launch promotion is active. */
@Composable
fun PlanChooserScreen(model: AppModel) {
    val scope = rememberCoroutineScope()
    val plans = rememberLoad(model) { model.api.plans() to runCatching { model.api.billingCatalog() }.getOrNull() }
    var busy by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    OnboardingColumn {
        Text(tx("Elegí tu suscripción", "Choose your subscription"), style = MaterialTheme.typography.headlineSmall, color = Dincr.colors.text, modifier = Modifier.semantics { heading() })
        LoadContent(plans) { (options, catalog) ->
            val promotionActive = catalog?.promotion?.active == true || options.any { it.promotion?.active == true }
            if (promotionActive) (catalog?.promotion?.message ?: catalog?.notice)?.let { StatusBanner(BannerTone.INFO, tx("Promoción de lanzamiento", "Launch promotion"), it) }
            options.forEach { option ->
                PlanCard(option, catalog, promotionActive, busy == option.code, enabled = busy == null) {
                    busy = option.code; error = null
                    scope.launch {
                        model.load(tx("No pudimos guardar tu suscripción.", "We couldn’t save your subscription.")) {
                            model.api.choosePlan(PlanChangeRequest(option.code, consentVersion = PLAN_CONSENT_VERSION))
                        }.onSuccess { result -> (result.profile ?: model.api.me()).let { model.apply(it) } }
                            .onFailure { if (it !is AuthException.SignedOut) error = it.message }
                        busy = null
                    }
                }
            }
        }
        error?.let { ErrorState(it) }
        TextButton({ model.signOut() }, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) { Text(tx("Cerrar sesión", "Sign out"), color = Dincr.colors.tint) }
    }
}

@Composable
fun PlanCard(option: PlanOption, catalog: BillingCatalog?, promotionActive: Boolean, busy: Boolean, enabled: Boolean, current: Boolean = false, actionLabel: String? = null, onChoose: (() -> Unit)?) {
    val paid = option.code != "free"
    val price = catalog?.plans?.firstOrNull { it.code == option.code }?.regularPriceCrc ?: option.regularPriceCrc
    DincrCard {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(option.name ?: option.code.uppercase(), style = MaterialTheme.typography.titleLarge, color = Dincr.colors.text, modifier = Modifier.weight(1f))
                if (current) PlanBadge(tx("Tu suscripción", "Your subscription"))
            }
            option.tagline?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2) }
            Text(
                when {
                    !paid -> tx("Gratis", "Free")
                    price != null -> "₡" + "%,d".format(price).replace(',', '.') + tx(" al mes", " per month")
                    else -> ""
                },
                style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text,
            )
            option.features.forEach { feature ->
                Row(verticalAlignment = Alignment.Top) {
                    Icon(Icons.Rounded.Check, contentDescription = null, tint = Dincr.colors.positive, modifier = Modifier.size(18.dp).padding(top = 2.dp))
                    Text(feature, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text, modifier = Modifier.padding(start = DincrSpacing.s2))
                }
            }
            when {
                onChoose == null || current -> Unit
                paid && !promotionActive -> Text(tx("Próximamente en las tiendas", "Coming soon to the stores"), style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.textMuted)
                else -> DincrPrimaryButton(actionLabel ?: tx("Elegir ${option.name ?: option.code}", "Choose ${option.name ?: option.code}"), onChoose, loading = busy, enabled = enabled)
            }
        }
    }
}

/** A13 — the app is locked: unlock with biometrics / screen lock, or sign out. */
@Composable
fun LockScreen(model: AppModel) {
    val activity = androidx.activity.compose.LocalActivity.current as? FragmentActivity
    var message by remember { mutableStateOf<String?>(null) }
    val prompt = { activity?.let { model.appLock.authenticate(it) { error -> message = error } } ?: Unit }
    LaunchedEffect(Unit) { prompt() }
    Box(Modifier.fillMaxSize().background(Dincr.colors.bg).clickable(enabled = false) {}) {
        GateScreen(Icons.Rounded.Fingerprint, tx("DINCR está bloqueado", "DINCR is locked"),
            message ?: tx("Desbloqueá con tu biometría o el bloqueo de tu teléfono.", "Unlock with your biometrics or your phone’s lock."),
            primary = tx("Desbloquear", "Unlock") to { prompt(); Unit }, onSignOut = { model.signOut() })
    }
}

/** A12 — one-time offer to turn on the app lock after signing in. */
@Composable
fun AppLockOffer(model: AppModel, onDone: () -> Unit) {
    val lock = model.appLock
    val activity = androidx.activity.compose.LocalActivity.current as? FragmentActivity
    if (lock.availability == AppLock.Availability.UNSUPPORTED) { LaunchedEffect(Unit) { lock.markOnboardingSeen(); onDone() }; return }
    androidx.compose.material3.AlertDialog(
        onDismissRequest = { lock.markOnboardingSeen(); onDone() },
        icon = { Icon(Icons.Rounded.Fingerprint, contentDescription = null, tint = Dincr.colors.tint) },
        title = { Text(tx("Protegé DINCR", "Protect DINCR")) },
        text = {
            Text(
                if (lock.availability == AppLock.Availability.NOT_ENROLLED) tx("Configurá un bloqueo de pantalla en tu teléfono y activá el bloqueo de DINCR desde Perfil → Seguridad.", "Set up a screen lock on your phone, then turn on the DINCR lock in Profile → Security.")
                else tx("Pedí tu biometría o el bloqueo del teléfono al abrir DINCR y después de 5 minutos fuera de la app.", "Ask for your biometrics or phone lock when opening DINCR and after 5 minutes away."),
                textAlign = TextAlign.Start,
            )
        },
        confirmButton = {
            // Turned on only after one successful unlock, so nobody locks themselves out.
            if (lock.availability == AppLock.Availability.AVAILABLE && activity != null) TextButton({
                lock.authenticate(activity) { error -> if (error == null) { lock.setEnabled(true); onDone() } }
            }) { Text(tx("Activar", "Turn on")) }
        },
        dismissButton = { TextButton({ lock.markOnboardingSeen(); onDone() }) { Text(tx("Ahora no", "Not now")) } },
    )
}

@Composable
fun RoundedIcon(icon: androidx.compose.ui.graphics.vector.ImageVector) {
    Box(Modifier.size(48.dp).background(Dincr.colors.tintContainer, RoundedCornerShape(DincrRadius.md)), contentAlignment = Alignment.Center) {
        Icon(icon, contentDescription = null, tint = Dincr.colors.onTintContainer)
    }
}

@Composable
fun VerticalGap() = Spacer(Modifier.size(DincrSpacing.s2))
