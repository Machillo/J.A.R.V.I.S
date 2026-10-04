package com.dincr.app.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Email
import androidx.compose.material.icons.rounded.MarkEmailRead
import androidx.compose.material3.Checkbox
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AppLanguage
import com.dincr.data.AuthException
import com.dincr.data.MailCandidate
import com.dincr.data.MailReturn
import com.dincr.data.MailStatus
import com.dincr.data.MessageKind
import com.dincr.data.OpsFlag
import com.dincr.data.OwnTransferRequest
import com.dincr.data.OwnTransferSuggestions
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.DincrMessage
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.EmptyState
import com.dincr.design.ErrorState
import kotlinx.coroutines.launch

private data class MailData(val status: MailStatus, val candidates: List<MailCandidate>, val transfers: OwnTransferSuggestions)

/**
 * H1–H6 — mail automation (VIP): connection, sync and review of the bank notices DINCR detected.
 * Nothing is saved without the user's review; a notice in another currency needs the user's own
 * exchange rate (DINCR never invents one); a currency DINCR cannot convert can only be rejected.
 */
@Composable
fun MailScreen(model: AppModel, nav: Navigator) {
    val data = rememberLoad(model) {
        val status = model.api.mailStatus()
        MailData(status, if (status.connected) model.api.mailCandidates(pendingOnly = true) else emptyList(),
            if (status.connected) runCatching { model.api.ownTransferSuggestions() }.getOrDefault(OwnTransferSuggestions()) else OwnTransferSuggestions())
    }
    // The browser returns here after connecting: reload whenever the app comes back.
    LifecycleResumeEffect(Unit) { data.reload(); onPauseOrDispose { } }
    val reviewer = rememberCandidateReviewer(model) { data.reload() }
    var syncing by remember { mutableStateOf(false) }
    var disconnect by remember { mutableStateOf<MailStatus.Connection?>(null) }
    val scope = rememberCoroutineScope()

    DetailScaffold(tx("Correos financieros", "Financial emails"), nav::back) {
        if (!model.isOn(OpsFlag.GMAIL_AUTOMATION)) { FeaturePaused(model, OpsFlag.GMAIL_AUTOMATION); return@DetailScaffold }
        LoadContent(data) { (status, candidates, transfers) ->
            if (!status.connected) ConnectMail(model, status) else {
                if (status.needsReauthorization) DincrMessage(MessageKind.TECHNICAL_ERROR, tx("Volvé a conectar tu correo", "Reconnect your mail"), tx("El permiso venció o fue revocado.", "The permission expired or was revoked."))
                DincrCard {
                    Column {
                        status.visibleConnections.forEach { c ->
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Column(Modifier.weight(1f)) {
                                    Text(c.email ?: tx("Correo conectado", "Connected mail"), style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text)
                                    Caption(listOfNotNull(if (c.provider == "microsoft") "Outlook" else "Gmail", c.importSince?.let { tx("desde ", "since ") + dateLabel(it) }).joinToString(" · "))
                                }
                                TextButton({ disconnect = c }, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Desconectar", "Disconnect"), color = Dincr.colors.negative) }
                            }
                        }
                        DincrPrimaryButton(tx("Buscar avisos nuevos", "Check for new notices"), loading = syncing, onClick = {
                            syncing = true
                            scope.launch {
                                model.load(tx("No pudimos revisar tu correo.", "We couldn’t check your mail.")) { model.api.syncMail() }
                                    .onSuccess { r ->
                                        val found = tx("Encontramos ${r.found ?: 0} avisos: ${r.pending ?: 0} por revisar.", "Found ${r.found ?: 0} notices: ${r.pending ?: 0} to review.")
                                        val failed = r.failedConnections.size
                                        model.showNotice(if (failed == 0) found else found + " " + tx("No pudimos revisar $failed de tus correos; intentá de nuevo más tarde.", "We couldn’t check $failed of your mailboxes; try again later."))
                                    }
                                    .onFailure { if (it !is AuthException.SignedOut) model.showNotice(it.message.orEmpty()) }
                                syncing = false; data.reload()
                            }
                        })
                    }
                }
                transfers.items.takeIf { it.isNotEmpty() }?.let { OwnTransfers(model, it) { data.reload() } }
                SectionTitle(tx("Por revisar", "To review"))
                val visible = candidates.filter { it.isPending }.let { list -> list.filter { c -> c.relatedCandidateId == null || list.none { it.candidateId == c.relatedCandidateId && (it.candidateId ?: 0) < (c.candidateId ?: 0) } } }
                if (visible.isEmpty()) EmptyState(Icons.Rounded.MarkEmailRead, tx("Todo revisado", "All reviewed"), tx("Cuando llegue un aviso de tu banco aparecerá acá para que lo confirmés.", "When a bank notice arrives it will appear here for you to confirm."))
                visible.forEach { candidate -> CandidateRow(candidate, reviewer) }
            }
        }
    }
    CandidateCorrectionHost(reviewer)
    disconnect?.let { c ->
        ConfirmDialog(tx("¿Desconectar ${c.email ?: "tu correo"}?", "Disconnect ${c.email ?: "your mail"}?"), tx("DINCR deja de leer ese buzón y revoca el permiso. Tus movimientos guardados no se borran.", "DINCR stops reading that mailbox and revokes the permission. Saved transactions stay."),
            tx("Desconectar", "Disconnect"), onDismiss = { disconnect = null }, onConfirm = {
                disconnect = null
                scope.launch {
                    model.load(tx("No pudimos desconectarlo.", "We couldn’t disconnect it.")) { model.api.disconnectMail(c.id) }
                        .onFailure { if (it !is AuthException.SignedOut) model.showNotice(it.message.orEmpty()) }
                    data.reload()
                }
            })
    }
}

/** H2 — consent, history scope and provider; the connection happens in the system browser. */
@Composable
private fun ConnectMail(model: AppModel, status: MailStatus) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var consent by remember { mutableStateOf(status.consent?.required != true) }
    var scopeChoice by remember { mutableStateOf("current_month") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    EmptyState(Icons.Rounded.Email, tx("Conectá tu correo", "Connect your mail"),
        tx("DINCR lee solo los avisos de tus bancos (permiso de solo lectura), te propone el movimiento y vos decidís si guardarlo.", "DINCR reads only your banks’ notices (read-only permission), suggests the transaction and you decide whether to save it."))
    if (status.consent?.required == true) Row(Modifier.fillMaxWidth().heightIn(min = 56.dp).toggleable(consent, role = Role.Checkbox) { consent = it }, verticalAlignment = Alignment.CenterVertically) {
        Checkbox(consent, null)
        Text(tx("Autorizo a DINCR a leer los avisos financieros de mi correo en modo solo lectura.", "I allow DINCR to read the financial notices in my mail, read-only."), style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text)
    }
    ChoiceChips(listOf("current_month" to tx("Este mes", "This month"), "current_year" to tx("Este año", "This year")), scopeChoice, { scopeChoice = it }, tx("Historia a revisar", "History to review"))
    error?.let { ErrorState(it) }
    fun connect(provider: MailReturn.Provider) {
        if (!consent || busy) return
        busy = true; error = null
        scope.launch {
            model.load(tx("No pudimos iniciar la conexión.", "We couldn’t start the connection.")) {
                status.consent?.takeIf { it.required }?.version?.let { model.api.acceptMailConsent(it) }
                model.api.connectMail(provider, scopeChoice, AppLanguage.current())
            }.onSuccess { response ->
                if (response.authorizationUrl.startsWith("https://")) openInBrowser(context, response.authorizationUrl)
                else error = tx("La dirección de conexión no es segura.", "The connection address is not secure.")
            }.onFailure { if (it !is AuthException.SignedOut) error = it.message }
            busy = false
        }
    }
    DincrPrimaryButton(tx("Conectar Gmail", "Connect Gmail"), { connect(MailReturn.Provider.GMAIL) }, enabled = consent, loading = busy)
    if (status.microsoftAvailable) TextButton({ connect(MailReturn.Provider.MICROSOFT) }, enabled = consent && !busy, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) {
        Text(tx("Conectar Outlook", "Connect Outlook"), color = Dincr.colors.tint)
    }
}

/** H6 — two notices of the same money moving between the user's own accounts. */
@Composable
private fun OwnTransfers(model: AppModel, items: List<OwnTransferSuggestions.Pair_>, onDone: () -> Unit) {
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    SectionTitle(tx("Transferencias entre tus cuentas", "Transfers between your accounts"))
    items.forEach { pair ->
        val first = pair.first ?: return@forEach
        val second = pair.second ?: return@forEach
        val declared = OwnTransferRequest.unknownDirection(first.direction, second.direction)
        DincrCard {
            Column {
                Caption(tx("Estos dos avisos parecen el mismo dinero moviéndose entre cuentas tuyas.", "These two notices look like the same money moving between your accounts."))
                listOf(first, second).forEach { side ->
                    val known = side.direction == "in" || side.direction == "out"
                    // A notice without a direction is shown with the one it will be saved with.
                    val direction = if (known) side.direction else declared?.takeIf { it != OwnTransferRequest.CANNOT_INFER }
                    val label = when (direction) { "in" -> tx("entra", "in"); "out" -> tx("sale", "out"); else -> "?" } +
                        if (!known && direction != null) tx(" (deducido)", " (inferred)") else ""
                    AmountLine("${side.bank.orEmpty()} · ${dateLabel(side.date)} · $label", side.amount, currency = side.currency)
                }
                if (declared == OwnTransferRequest.CANNOT_INFER) {
                    Caption(tx("No sabemos en qué dirección se movió el dinero. Revisá estos avisos por separado.", "We don’t know which way the money moved. Review these notices separately."))
                    return@Column
                }
                TextButton(enabled = !busy, onClick = {
                    val id = first.candidateId ?: return@TextButton
                    val counterpart = second.candidateId ?: return@TextButton
                    busy = true
                    scope.launch {
                        model.load(tx("No pudimos confirmarlo.", "We couldn’t confirm it.")) {
                            model.api.confirmOwnTransfer(id, OwnTransferRequest(counterpart, true, declared))
                        }.onFailure { if (it !is AuthException.SignedOut) model.showNotice(it.message.orEmpty()) }
                        busy = false; onDone()
                    }
                }, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Son mis cuentas: no es gasto ni ingreso", "They’re my accounts: not spending or income"), color = Dincr.colors.tint) }
            }
        }
    }
}
