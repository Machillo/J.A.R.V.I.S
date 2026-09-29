package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AccountBalance
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
import com.dincr.data.AmountInput
import com.dincr.data.ApiError
import com.dincr.data.AuthException
import com.dincr.data.CandidateCorrection
import com.dincr.data.CandidateReviewResult
import com.dincr.data.ExchangeRateInput
import com.dincr.data.FinancialIdentity
import com.dincr.data.MailCandidate
import com.dincr.data.MailReturn
import com.dincr.data.MailStatus
import com.dincr.data.OpsFlag
import com.dincr.data.OwnTransferRequest
import com.dincr.data.OwnTransferSuggestions
import com.dincr.design.BannerTone
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.EmptyState
import com.dincr.design.ErrorState
import com.dincr.design.MoneyText
import com.dincr.design.StatusBanner
import com.dincr.design.generated.DincrSpacing
import java.time.LocalDate
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
    var reviewing by remember { mutableStateOf<Long?>(null) }
    var correcting by remember { mutableStateOf<MailCandidate?>(null) }
    var syncing by remember { mutableStateOf(false) }
    var feedback by remember { mutableStateOf<Pair<Long, String>?>(null) }
    var disconnect by remember { mutableStateOf<MailStatus.Connection?>(null) }
    val scope = rememberCoroutineScope()

    /**
     * One review at a time. A success is reported only when the stored status is the one asked for
     * and the backend did not answer `already_reviewed`; an ambiguous outcome reloads the list and
     * reports what is really stored.
     */
    fun review(candidate: MailCandidate, action: suspend () -> CandidateReviewResult, expected: String) {
        val id = candidate.candidateId ?: return
        if (reviewing != null) return
        reviewing = id
        scope.launch {
            val result = model.load(tx("No pudimos completar la revisión.", "We couldn’t complete the review.")) { action() }
            result.onSuccess { r ->
                // The card leaves the pending list on reload, so the outcome is announced app-wide.
                model.showNotice(when {
                    r.alreadyReviewed == true -> tx("Este aviso ya estaba revisado; no cambió nada.", "This notice was already reviewed; nothing changed.")
                    r.status == expected -> if (expected == "rejected") tx("Aviso descartado.", "Notice dismissed.") else tx("Movimiento guardado.", "Transaction saved.")
                    else -> tx("El aviso quedó como «${r.status}».", "The notice is now “${r.status}”.")
                })
                feedback = null
                correcting = null
            }.onFailure { error ->
                if (error is AuthException.SignedOut) return@onFailure
                val api = error as? ApiError
                feedback = id to (if (api?.kind == ApiError.Kind.VALIDATION) error.message.orEmpty()
                else tx("No sabemos si se guardó. Actualizamos la lista para mostrar lo que quedó registrado.", "We’re not sure it was saved. The list was refreshed to show what’s stored."))
            }
            reviewing = null
            data.reload()
        }
    }

    DetailScaffold(tx("Correos financieros", "Financial emails"), nav::back) {
        if (!model.isOn(OpsFlag.GMAIL_AUTOMATION)) { FeaturePaused(model, OpsFlag.GMAIL_AUTOMATION); return@DetailScaffold }
        LoadContent(data) { (status, candidates, transfers) ->
            if (!status.connected) ConnectMail(model, status) else {
                if (status.needsReauthorization) StatusBanner(BannerTone.WARNING, tx("Volvé a conectar tu correo", "Reconnect your mail"), tx("El permiso venció o fue revocado.", "The permission expired or was revoked."))
                DincrCard {
                    Column {
                        status.connections.forEach { c ->
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
                                    .onSuccess { r -> model.showNotice(tx("Encontramos ${r.found ?: 0} avisos: ${r.pending ?: 0} por revisar.", "Found ${r.found ?: 0} notices: ${r.pending ?: 0} to review.")) }
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
                visible.forEach { candidate ->
                    CandidateCard(candidate, busy = reviewing == candidate.candidateId, message = feedback?.takeIf { it.first == candidate.candidateId }?.second,
                        onAccept = { review(candidate, { model.api.acceptCandidate(candidate.candidateId!!) }, "confirmed") },
                        onCorrect = { correcting = candidate },
                        onReject = { review(candidate, { model.api.rejectCandidate(candidate.candidateId!!) }, "rejected") })
                }
            }
        }
    }
    correcting?.let { candidate ->
        CorrectionSheet(candidate, saving = reviewing == candidate.candidateId, onDismiss = { correcting = null }) { correction ->
            review(candidate, { model.api.correctCandidate(candidate.candidateId!!, correction) }, "confirmed")
        }
    }
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
                model.api.connectMail(provider, scopeChoice)
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

@Composable
private fun CandidateCard(candidate: MailCandidate, busy: Boolean, message: String?, onAccept: () -> Unit, onCorrect: () -> Unit, onReject: () -> Unit) {
    DincrCard {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(candidate.description ?: candidate.subject.orEmpty(), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
                    Caption(listOfNotNull(candidate.bank, dateLabel(candidate.transactionDate), candidate.category).joinToString(" · "))
                }
                // Always in the notice's own currency.
                MoneyText(candidate.nativeAmount, currency = candidate.nativeCurrency,
                    sign = if (candidate.transactionType == "income") com.dincr.data.MoneyFormat.Sign.INCOME else com.dincr.data.MoneyFormat.Sign.NONE)
            }
            when {
                candidate.cannotConvert -> Caption(tx("Este aviso está en ${candidate.nativeCurrency}, una moneda que DINCR no convierte. Solo podés descartarlo.", "This notice is in ${candidate.nativeCurrency}, a currency DINCR doesn’t convert. You can only dismiss it."))
                candidate.needsRate -> Caption(tx("Está en ${candidate.nativeCurrency}: tocá Corregir e indicá tu tipo de cambio.", "It’s in ${candidate.nativeCurrency}: tap Correct and enter your exchange rate."))
            }
            candidate.resolutionReason?.let { Caption(it) }
            message?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2) }
            Row(horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
                if (!candidate.needsRate && !candidate.cannotConvert) TextButton(onAccept, enabled = !busy, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Confirmar", "Confirm"), color = Dincr.colors.tint) }
                if (!candidate.cannotConvert) TextButton(onCorrect, enabled = !busy, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Corregir", "Correct"), color = Dincr.colors.tint) }
                TextButton(onReject, enabled = !busy, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Descartar", "Dismiss"), color = Dincr.colors.negative) }
            }
        }
    }
}

/** Accept with corrections: every field is sent (the category too, or it would reset). */
@Composable
private fun CorrectionSheet(candidate: MailCandidate, saving: Boolean, onDismiss: () -> Unit, onSubmit: (CandidateCorrection) -> Unit) {
    val format = Dincr.money
    val native = candidate.nativeCurrency ?: candidate.accountBaseCurrency ?: "CRC"
    var amount by remember { mutableStateOf(candidate.nativeAmount?.let(format::inputText).orEmpty()) }
    var description by remember { mutableStateOf(candidate.description ?: candidate.subject.orEmpty()) }
    var category by remember { mutableStateOf(candidate.category ?: "") }
    var type by remember { mutableStateOf(candidate.transactionType?.takeIf { it in setOf("expense", "income", "debt_payment") } ?: "expense") }
    var date by remember { mutableStateOf(candidate.transactionDate?.let { runCatching { LocalDate.parse(it.take(10)) }.getOrNull() } ?: LocalDate.now()) }
    var rate by remember { mutableStateOf("") }
    var errors by remember { mutableStateOf(mapOf<String, String>()) }
    FormSheet(tx("Corregir y guardar", "Correct and save"), saving, null, tx("Guardar", "Save"), onDismiss = onDismiss, onPrimary = {
        val found = mutableMapOf<String, String>()
        val amountValue = AmountInput.parse(amount, format.separators).also { if (it == null) found["amount"] = tx("Monto no válido.", "Not a valid amount.") }
        val rateValue = if (candidate.needsRate) ExchangeRateInput.parse(rate, format.separators).also { if (it == null) found["rate"] = tx("Escribí cuántos colones vale 1 dólar.", "Enter how many colones 1 dollar is worth.") } else null
        if (description.isBlank()) found["description"] = tx("Escribí una descripción.", "Enter a description.")
        if (category.isBlank()) found["category"] = tx("Escribí una categoría.", "Enter a category.")
        errors = found
        if (found.isNotEmpty() || amountValue == null) return@FormSheet
        onSubmit(CandidateCorrection(date.toString(), description.trim(), amountValue, type, category.trim(), rateValue))
    }) {
        MoneyField(tx("Monto (en $native)", "Amount (in $native)"), amount, { amount = it }, errors["amount"], symbol = format.copy(currency = native).symbol)
        if (candidate.needsRate) FormField(tx("Tipo de cambio (₡ por US$1)", "Exchange rate (₡ per US$1)"), rate, { rate = it }, errors["rate"], androidx.compose.ui.text.input.KeyboardType.Decimal,
            supporting = tx("El de tu banco. DINCR no lo inventa.", "Your bank’s. DINCR never makes one up."))
        FormField(tx("Descripción", "Description"), description, { description = it }, errors["description"])
        FormField(tx("Categoría", "Category"), category, { category = it }, errors["category"])
        ChoiceChips(listOf("expense" to tx("Gasto", "Expense"), "income" to tx("Ingreso", "Income"), "debt_payment" to tx("Pago de deuda", "Debt payment")), type, { type = it }, tx("Tipo", "Type"))
        DateField(tx("Fecha", "Date"), date, { it?.let { date = it } })
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
        DincrCard {
            Column {
                Caption(tx("Estos dos avisos parecen el mismo dinero moviéndose entre cuentas tuyas.", "These two notices look like the same money moving between your accounts."))
                listOf(first, second).forEach { side -> AmountLine("${side.bank.orEmpty()} · ${dateLabel(side.date)} · ${if (side.direction == "in") tx("entra", "in") else if (side.direction == "out") tx("sale", "out") else "?"}", side.amount, currency = side.currency) }
                TextButton(enabled = !busy, onClick = {
                    val id = first.candidateId ?: return@TextButton
                    val counterpart = second.candidateId ?: return@TextButton
                    busy = true
                    scope.launch {
                        model.load(tx("No pudimos confirmarlo.", "We couldn’t confirm it.")) {
                            model.api.confirmOwnTransfer(id, OwnTransferRequest(counterpart, true, if (first.direction == "unknown") "out" else null))
                        }.onFailure { if (it !is AuthException.SignedOut) model.showNotice(it.message.orEmpty()) }
                        busy = false; onDone()
                    }
                }, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Son mis cuentas: no es gasto ni ingreso", "They’re my accounts: not spending or income"), color = Dincr.colors.tint) }
            }
        }
    }
}

/** H7 — accounts detected in the notices: confirm which are the user's own. */
@Composable
fun AccountsScreen(model: AppModel, nav: Navigator) {
    val identity = rememberLoad(model) { model.api.financialIdentity() }
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf<Long?>(null) }
    DetailScaffold(tx("Cuentas detectadas", "Detected accounts"), nav::back) {
        if (!model.isOn(OpsFlag.GMAIL_AUTOMATION)) { FeaturePaused(model, OpsFlag.GMAIL_AUTOMATION); return@DetailScaffold }
        LoadContent(identity) { data: FinancialIdentity ->
            if (data.items.isEmpty()) EmptyState(Icons.Rounded.AccountBalance, tx("Sin cuentas detectadas", "No accounts detected"), tx("Las cuentas aparecen cuando DINCR procesa avisos de tu banco.", "Accounts appear when DINCR processes notices from your bank."))
            data.items.forEach { account ->
                DincrCard {
                    Column {
                        Text(listOfNotNull(account.bankName, account.accountName).joinToString(" · "), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
                        Caption(listOfNotNull(account.currency, account.accountLast4?.let { "••$it" }, when (account.ownershipStatus) { "own" -> tx("Tuya", "Yours"); "not_mine" -> tx("No es tuya", "Not yours"); else -> tx("Sin confirmar", "Unconfirmed") }).joinToString(" · "))
                        Row {
                            listOf(true to tx("Es mía", "It’s mine"), false to tx("No es mía", "Not mine")).forEach { (own, label) ->
                                TextButton(enabled = busy == null, onClick = {
                                    busy = account.id
                                    scope.launch {
                                        model.load(tx("No pudimos guardarlo.", "We couldn’t save it.")) { model.api.setAccountOwnership(account.id, own) }
                                            .onFailure { if (it !is AuthException.SignedOut) model.showNotice(it.message.orEmpty()) }
                                        busy = null; identity.reload()
                                    }
                                }, modifier = Modifier.heightIn(min = 48.dp)) { Text(label, color = Dincr.colors.tint) }
                            }
                        }
                    }
                }
            }
        }
    }
}
