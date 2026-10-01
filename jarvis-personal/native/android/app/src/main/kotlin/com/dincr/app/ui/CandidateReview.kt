package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AmountInput
import com.dincr.data.ApiError
import com.dincr.data.AuthException
import com.dincr.data.BankBranding
import com.dincr.data.CandidateCorrection
import com.dincr.data.CandidateReviewResult
import com.dincr.data.ExchangeRateInput
import com.dincr.data.MailCandidate
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.MoneyText
import com.dincr.design.generated.DincrSpacing
import java.time.LocalDate
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch

/**
 * The review of the bank notices DINCR detected, shared by its two surfaces: Email Monitor (Correos)
 * and Cuentas. Same endpoints, same states (pending, auto_saved, confirmed, rejected, duplicate),
 * one review at a time. A success is reported only when the stored status is the one asked for and
 * the backend did not answer `already_reviewed`; an ambiguous outcome reloads the list and reports
 * what is really stored.
 */
class CandidateReviewer(private val model: AppModel, private val scope: CoroutineScope, private val onDone: () -> Unit) {
    var reviewing by mutableStateOf<Long?>(null)
        private set
    var feedback by mutableStateOf<Pair<Long, String>?>(null)
        private set
    var correcting by mutableStateOf<MailCandidate?>(null)

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
            onDone()
        }
    }

    fun accept(candidate: MailCandidate) = review(candidate, { model.api.acceptCandidate(candidate.candidateId!!) }, "confirmed")
    fun reject(candidate: MailCandidate) = review(candidate, { model.api.rejectCandidate(candidate.candidateId!!) }, "rejected")
    fun correct(candidate: MailCandidate, correction: CandidateCorrection) =
        review(candidate, { model.api.correctCandidate(candidate.candidateId!!, correction) }, "confirmed")
}

@Composable
fun rememberCandidateReviewer(model: AppModel, onDone: () -> Unit): CandidateReviewer {
    val scope = rememberCoroutineScope()
    val latest = rememberUpdatedState(onDone)
    return remember(model) { CandidateReviewer(model, scope) { latest.value() } }
}

/** A notice with the review actions when pending, or its stored state otherwise. */
@Composable
fun CandidateRow(candidate: MailCandidate, reviewer: CandidateReviewer) {
    CandidateCard(candidate, busy = reviewer.reviewing == candidate.candidateId, message = reviewer.feedback?.takeIf { it.first == candidate.candidateId }?.second,
        onAccept = { reviewer.accept(candidate) }, onCorrect = { reviewer.correcting = candidate }, onReject = { reviewer.reject(candidate) })
}

/** The correction sheet of the candidate being corrected, if any. */
@Composable
fun CandidateCorrectionHost(reviewer: CandidateReviewer) {
    reviewer.correcting?.let { candidate ->
        CorrectionSheet(candidate, saving = reviewer.reviewing == candidate.candidateId, onDismiss = { reviewer.correcting = null }) { correction ->
            reviewer.correct(candidate, correction)
        }
    }
}

fun reviewStatusLabel(status: String?): String? = when (status) {
    "confirmed" -> tx("Confirmado", "Confirmed")
    "auto_saved" -> tx("Guardado automáticamente", "Saved automatically")
    "rejected" -> tx("Descartado", "Dismissed")
    "duplicate" -> tx("Duplicado", "Duplicate")
    "pending" -> tx("Por revisar", "To review")
    else -> null
}

@Composable
fun CandidateCard(candidate: MailCandidate, busy: Boolean, message: String?, onAccept: () -> Unit, onCorrect: () -> Unit, onReject: () -> Unit) {
    DincrCard {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                // The logo only when the bank is identified; the name stays in the text below.
                val bank = BankBranding.identify(candidate.bank)
                bank?.let { BankLogo(it, size = 32.dp, modifier = Modifier.padding(end = DincrSpacing.s2)) }
                Column(Modifier.weight(1f)) {
                    Text(candidate.description ?: candidate.subject.orEmpty(), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
                    // `bank` is the institution code: shown as the bank's name when it is identified.
                    Caption(listOfNotNull(bank?.name ?: candidate.bank?.takeIf { it.isNotBlank() }, dateLabel(candidate.transactionDate), candidate.category).joinToString(" · "))
                }
                // Always in the notice's own currency.
                MoneyText(candidate.nativeAmount, currency = candidate.nativeCurrency,
                    sign = if (candidate.transactionType == "income") com.dincr.data.MoneyFormat.Sign.INCOME else com.dincr.data.MoneyFormat.Sign.NONE)
            }
            if (!candidate.isPending) {
                reviewStatusLabel(candidate.reviewStatus)?.let { Text(it, style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2) }
                return@Column
            }
            when {
                candidate.cannotConvert -> Caption(tx("Este aviso está en ${candidate.nativeCurrency}, una moneda que DINCR no convierte. Solo podés descartarlo.", "This notice is in ${candidate.nativeCurrency}, a currency DINCR doesn’t convert. You can only dismiss it."))
                candidate.needsRate -> Caption(tx("Está en ${candidate.nativeCurrency}: tocá Corregir e indicá tu tipo de cambio.", "It’s in ${candidate.nativeCurrency}: tap Correct and enter your exchange rate."))
            }
            when (candidate.resolutionNote) {
                MailCandidate.ResolutionNote.POSSIBLE_MATCH -> Caption(tx("Posible coincidencia con otro aviso bancario o estado de cuenta. DINCR lo deja para tu revisión en vez de descartarlo solo.", "Possible match with another bank notice or statement. DINCR leaves it for your review instead of dismissing it on its own."))
                MailCandidate.ResolutionNote.PAIRED_OWN_TRANSFER -> Caption(tx("Dos avisos corresponden a un traslado entre tus cuentas confirmadas. Al confirmar, no se suma a ingresos ni gastos.", "Two notices describe a transfer between your confirmed accounts. Confirming won’t add income or expense."))
                MailCandidate.ResolutionNote.OWN_ACCOUNTS -> Caption(tx("Ambas cuentas son de las que confirmaste como tuyas. Al confirmar, no se registra como ingreso ni gasto.", "Both accounts are ones you confirmed as yours. Confirming won’t record income or expense."))
                null -> Unit
            }
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
fun CorrectionSheet(candidate: MailCandidate, saving: Boolean, onDismiss: () -> Unit, onSubmit: (CandidateCorrection) -> Unit) {
    val format = Dincr.money
    val native = candidate.nativeCurrency ?: candidate.accountBaseCurrency ?: "CRC"
    var amount by remember { mutableStateOf(candidate.nativeAmount?.let(format::inputText).orEmpty()) }
    var description by remember { mutableStateOf(candidate.description ?: candidate.subject.orEmpty()) }
    var category by remember { mutableStateOf(candidate.category ?: "") }
    var type by remember { mutableStateOf(candidate.transactionType?.takeIf { it in setOf("expense", "income", "debt_payment", "transfer") } ?: "expense") }
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
        ChoiceChips(listOf("expense" to tx("Gasto", "Expense"), "income" to tx("Ingreso", "Income"), "debt_payment" to tx("Pago de deuda", "Debt payment"),
            "transfer" to tx("Transferencia", "Transfer")), type, { type = it }, tx("Tipo", "Type"))
        DateField(tx("Fecha", "Date"), date, { it?.let { date = it } })
    }
}
