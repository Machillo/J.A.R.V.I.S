package com.dincr.app.ui

import android.net.Uri
import androidx.browser.customtabs.CustomTabsIntent
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Shield
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.AppModel
import com.dincr.app.R
import com.dincr.app.tx
import com.dincr.data.OAuthProvider
import com.dincr.design.BannerTone
import com.dincr.design.Dincr
import com.dincr.design.ErrorState
import com.dincr.design.StatusBanner
import com.dincr.design.generated.DincrRadius
import com.dincr.design.generated.DincrSpacing

/** PARITY A2 — Google only on Android (Apple sign-in is iOS-only, as in Capacitor). */
@Composable
fun LoginScreen(model: AppModel) {
    val context = LocalContext.current
    val error by model.signInError.collectAsStateWithLifecycle()
    val signingIn by model.signingIn.collectAsStateWithLifecycle()
    Column(
        Modifier.fillMaxSize().safeDrawingPadding().verticalScroll(rememberScrollState()).padding(horizontal = DincrSpacing.s4),
        verticalArrangement = Arrangement.spacedBy(DincrSpacing.s6),
    ) {
        Row(Modifier.padding(top = DincrSpacing.s8), verticalAlignment = Alignment.CenterVertically) {
            BrandMark(44)
            Text("DINCR", style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text, letterSpacing = MaterialTheme.typography.titleMedium.letterSpacing * 4, modifier = Modifier.padding(start = DincrSpacing.s3))
        }
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
            Text(tx("Tu dinero, con propósito", "Your money, with purpose"), style = MaterialTheme.typography.displaySmall, color = Dincr.colors.text, modifier = Modifier.semantics { heading() })
            Text(tx("Ordená tus ingresos, gastos, deudas y metas, y sabé qué sigue.", "Organize your income, expenses, debts and goals, and know what comes next."), style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text2)
        }
        // Google branding: light button, official "G", #1F1F1F text, #747775 outline.
        OutlinedButton(
            onClick = {
                if (model.isFixtures) model.signInWithFixtures()
                else model.beginSignIn(OAuthProvider.GOOGLE)?.let { CustomTabsIntent.Builder().setShowTitle(true).build().launchUrl(context, Uri.parse(it)) }
            },
            enabled = !signingIn,
            modifier = Modifier.fillMaxWidth().widthIn(max = 600.dp).heightIn(min = 52.dp).testTag("login.google"),
            shape = RoundedCornerShape(DincrRadius.md),
            border = BorderStroke(1.dp, Color(0xFF747775)),
            colors = ButtonDefaults.outlinedButtonColors(containerColor = Color.White, contentColor = Color(0xFF1F1F1F)),
        ) {
            if (signingIn) CircularProgressIndicator(Modifier.size(20.dp), color = Color(0xFF1F1F1F), strokeWidth = 2.dp)
            else {
                Icon(painterResource(R.drawable.google_g), contentDescription = null, tint = Color.Unspecified, modifier = Modifier.size(20.dp))
                Text(tx("Continuar con Google", "Continue with Google"), style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Medium, modifier = Modifier.padding(start = DincrSpacing.s3))
            }
        }
        error?.let { ErrorState(it) }
        Row(verticalAlignment = Alignment.Top) {
            Icon(Icons.Rounded.Shield, contentDescription = null, tint = Dincr.colors.textMuted, modifier = Modifier.size(18.dp))
            Text(tx("Se abrirá una ventana segura para iniciar sesión. DINCR nunca ve tu contraseña.", "A secure window will open to sign in. DINCR never sees your password."),
                style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.textMuted, modifier = Modifier.padding(start = DincrSpacing.s2))
        }
        if (model.isFixtures) StatusBanner(BannerTone.INFO, tx("Modo de demostración", "Demo mode"), tx("Datos de ejemplo. No se conecta a ninguna cuenta real.", "Sample data. Not connected to any real account."))
    }
}
