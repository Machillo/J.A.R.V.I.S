package com.dincr.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ArrowBack
import androidx.compose.material.icons.rounded.CheckCircle
import androidx.compose.material.icons.rounded.Close
import androidx.compose.material3.Checkbox
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AccountOwnership
import com.dincr.data.AppLanguage
import com.dincr.data.AuthException
import com.dincr.data.BankBranding
import com.dincr.data.FinancialIdentity
import com.dincr.data.SearchText
import com.dincr.design.Dincr
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.DincrTonalButton
import com.dincr.design.generated.DincrSpacing
import kotlinx.coroutines.launch

private fun bankOf(account: FinancialIdentity.Account): BankBranding.Bank? =
    BankBranding.identify(account.institutionCode) ?: BankBranding.identify(account.bankName)

private fun detail(account: FinancialIdentity.Account, extra: String? = null): String =
    listOfNotNull(account.accountLast4?.let { "•••• $it" }, account.currency, extra).joinToString(" · ")

/** The codes the declaration knows by name; any other bank goes as "other" with its name. */
internal fun declaredCode(bank: BankBranding.Bank?): String = bank?.id?.takeIf { it in setOf("bac", "popular", "multimoney") } ?: "other"

/**
 * The Owner adds a bank (Cuentas → Agregar cuenta): pick it, confirm the accounts DINCR found in the
 * connected mail or add one by hand, and see what was added. It only uses Cuentas' own commands
 * (ownership answers, a declared own account), one per tap. No balance: a detected account's is
 * unknown. iOS: `AddBankFlow`.
 */
@Composable
internal fun AddBankFlow(model: AppModel, onDismiss: () -> Unit) {
    var bank by remember { mutableStateOf<BankBranding.Bank?>(null) }
    var added by remember { mutableStateOf<List<FinancialIdentity.Account>?>(null) }
    var query by remember { mutableStateOf("") }
    var found by remember { mutableStateOf<List<FinancialIdentity.Account>?>(null) }
    var chosen by remember { mutableStateOf(emptySet<Long>()) }
    var error by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    // The bank to declare by hand; `manualOther` is another institution.
    var manual by remember { mutableStateOf<BankBranding.Bank?>(null) }
    var manualOther by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val fallback = tx("No pudimos leer tus cuentas.", "We couldn’t read your accounts.")

    fun open(next: BankBranding.Bank) {
        bank = next; found = null; chosen = emptySet(); error = null
        scope.launch {
            model.load(fallback) { model.api.financialIdentity() }
                .onSuccess { identity ->
                    val accounts = identity.items.filter { bankOf(it)?.id == next.id && it.ownership != AccountOwnership.NOT_MINE }
                    found = accounts
                    chosen = accounts.filter { it.ownership == null }.map { it.id }.toSet()
                }
                .onFailure { if (it !is AuthException.SignedOut) error = it.message }
        }
    }

    Dialog(onDismissRequest = { if (!saving) onDismiss() }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Column(Modifier.fillMaxSize().background(Dincr.colors.bg).safeDrawingPadding().testTag("addBank")) {
            val current = bank
            val done = added
            Row(Modifier.fillMaxWidth().padding(horizontal = DincrSpacing.s2), verticalAlignment = Alignment.CenterVertically) {
                val backLabel = tx("Volver", "Back")
                if (current != null && done == null) IconButton({ bank = null }, Modifier.semantics { contentDescription = backLabel }) { Icon(Icons.AutoMirrored.Rounded.ArrowBack, null, tint = Dincr.colors.tint) }
                else Box(Modifier.size(48.dp))
                Text(when { done != null -> tx("Listo", "Done"); current != null -> current.name; else -> tx("Agregar cuenta", "Add account") },
                    Modifier.weight(1f), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text, textAlign = TextAlign.Center)
                val closeLabel = tx("Cerrar", "Close")
                IconButton(onDismiss, Modifier.testTag("addBank.close").semantics { contentDescription = closeLabel }) { Icon(Icons.Rounded.Close, null, tint = Dincr.colors.tint) }
            }
            Column(Modifier.weight(1f).fillMaxWidth().verticalScroll(rememberScrollState()).padding(DincrSpacing.s4), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s4)) {
                when {
                    done != null -> DoneStep(done)
                    current != null -> ReviewStep(current, found, chosen, error, onToggle = { id -> chosen = if (id in chosen) chosen - id else chosen + id }, onRetry = { open(current) }, onManual = { manual = current; manualOther = false })
                    else -> PickStep(query, { query = it }, ::open, onManual = { manual = null; manualOther = true })
                }
            }
            val accounts = found
            when {
                done != null -> Row(Modifier.fillMaxWidth().padding(DincrSpacing.s4), horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
                    Box(Modifier.weight(1f).testTag("addBank.another")) { DincrTonalButton(tx("Agregar otra", "Add another"), { added = null; bank = null; query = "" }, modifier = Modifier.fillMaxWidth()) }
                    Box(Modifier.weight(1f).testTag("addBank.finish")) { DincrPrimaryButton(tx("Listo", "Done"), onDismiss, modifier = Modifier.fillMaxWidth()) }
                }
                current != null && !accounts.isNullOrEmpty() -> Box(Modifier.fillMaxWidth().padding(DincrSpacing.s4).testTag("addBank.add")) {
                    DincrPrimaryButton(tx("Agregar", "Add"), {
                        saving = true; error = null
                        scope.launch {
                            // One ownership answer per chosen account, then the backend's list says what is now the Owner's.
                            model.load(tx("No pudimos guardarlo.", "We couldn’t save it.")) {
                                chosen.forEach { model.api.setAccountOwnership(it, AccountOwnership.OWN) }
                                model.api.financialIdentity()
                            }.onSuccess { identity ->
                                val ids = accounts.map { it.id }.toSet()
                                added = identity.items.filter { it.id in ids && it.ownership == AccountOwnership.OWN }
                            }.onFailure { if (it !is AuthException.SignedOut) error = it.message }
                            saving = false
                        }
                    }, enabled = !saving && (chosen.isNotEmpty() || accounts.any { it.ownership == AccountOwnership.OWN }), modifier = Modifier.fillMaxWidth())
                }
            }
        }
    }
    val target = manual
    if (target != null || manualOther) {
        DeclareOwnAccountSheet(model, onDismiss = { manual = null; manualOther = false }, institutionCode = declaredCode(target), institutionLabel = if (declaredCode(target) == "other") target?.name.orEmpty() else "") { _ ->
            manual = null; manualOther = false
            if (target == null) onDismiss() else scope.launch {
                model.load(fallback) { model.api.financialIdentity() }
                    .onSuccess { identity -> added = identity.items.filter { it.ownership == AccountOwnership.OWN && bankOf(it)?.id == target.id } }
                    .onFailure { onDismiss() }
            }
        }
    }
}

@Composable
private fun PickStep(query: String, onQuery: (String) -> Unit, onBank: (BankBranding.Bank) -> Unit, onManual: () -> Unit) {
    val language = AppLanguage.current()
    val banks = BankBranding.onboardingInstitutions(language).filter { query.isBlank() || SearchText.matches(query, listOf(it.name)) }
    OutlinedTextField(query, onQuery, placeholder = { Text(tx("Buscá tu banco", "Search for your bank")) }, singleLine = true, shape = RoundedCornerShape(28.dp), modifier = Modifier.fillMaxWidth().testTag("addBank.search"))
    banks.chunked(2).forEach { row ->
        Row(horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
            row.forEach { institution ->
                val bank = BankBranding.identify(institution.logoId)
                Column(
                    Modifier.weight(1f).heightIn(min = 112.dp).background(Dincr.colors.surface, RoundedCornerShape(16.dp))
                        .testTag("addBank.bank.${bank?.id ?: institution.id}")
                        .clickable { bank?.let(onBank) }.padding(DincrSpacing.s3).semantics(mergeDescendants = true) {},
                    horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2, Alignment.CenterVertically),
                ) {
                    BankLogo(bank, size = 48.dp)
                    Text(institution.name, style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text, textAlign = TextAlign.Center, maxLines = 2)
                }
            }
            if (row.size == 1) Box(Modifier.weight(1f))
        }
    }
    if (banks.isEmpty()) Caption(tx("Ese banco no está en la lista. Podés agregarlo a mano.", "That bank isn’t on the list. You can add it by hand."))
    Box(Modifier.fillMaxWidth().testTag("addBank.manual")) { DincrTonalButton(tx("Agregar otra institución a mano", "Add another institution by hand"), onManual, modifier = Modifier.fillMaxWidth()) }
}

@Composable
private fun ReviewStep(bank: BankBranding.Bank, found: List<FinancialIdentity.Account>?, chosen: Set<Long>, error: String?, onToggle: (Long) -> Unit, onRetry: () -> Unit, onManual: () -> Unit) {
    if (error != null) {
        Text(error, color = Dincr.colors.negative, style = MaterialTheme.typography.bodyMedium)
        DincrTonalButton(tx("Intentar de nuevo", "Try again"), onRetry)
    }
    if (found == null) return
    Text(tx("Revisá tus cuentas", "Review your accounts"), style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold), color = Dincr.colors.text, modifier = Modifier.semantics { heading() })
    if (found.isEmpty()) {
        Text(tx("No encontré cuentas de ${bank.name} en tus correos. Podés agregarla a mano.", "I found no ${bank.name} accounts in your mail. You can add one by hand."),
            style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text2, modifier = Modifier.testTag("addBank.none"))
    } else {
        Text(tx("Las encontré en tus correos. Marcá las que son tuyas.", "I found these in your mail. Check the ones that are yours."), style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text2)
        Column(Modifier.fillMaxWidth().background(Dincr.colors.surface, RoundedCornerShape(16.dp)).padding(horizontal = DincrSpacing.s3, vertical = DincrSpacing.s1)) {
            found.forEach { account ->
                val own = account.ownership == AccountOwnership.OWN
                Row(Modifier.fillMaxWidth().heightIn(min = 64.dp).testTag("addBank.account.${account.id}").clickable(enabled = !own) { onToggle(account.id) }, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                    Checkbox(own || account.id in chosen, null, enabled = !own)
                    BankLogo(bank, size = 44.dp)
                    Column(Modifier.weight(1f)) {
                        Text(account.accountName ?: bank.name, style = MaterialTheme.typography.titleSmall, color = Dincr.colors.text)
                        Caption(detail(account, if (own) tx("Ya está agregada", "Already added") else null))
                    }
                }
            }
        }
    }
    Box(Modifier.fillMaxWidth().testTag("addBank.review.manual")) { DincrTonalButton(tx("Agregar una a mano", "Add one by hand"), onManual, modifier = Modifier.fillMaxWidth()) }
}

@Composable
private fun DoneStep(accounts: List<FinancialIdentity.Account>) {
    Column(Modifier.fillMaxWidth().background(HomeHero, RoundedCornerShape(16.dp)).padding(vertical = DincrSpacing.s6), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
        Icon(Icons.Rounded.CheckCircle, null, tint = Color.White, modifier = Modifier.size(56.dp))
        Text(if (accounts.size == 1) tx("1 cuenta en tu lista", "1 account on your list") else tx("${accounts.size} cuentas en tu lista", "${accounts.size} accounts on your list"),
            style = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold), color = Color.White, modifier = Modifier.testTag("addBank.done").semantics { heading() })
    }
    if (accounts.isNotEmpty()) Column(Modifier.fillMaxWidth().background(Dincr.colors.surface, RoundedCornerShape(16.dp)).padding(DincrSpacing.s3), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
        accounts.forEach { account ->
            Row(Modifier.fillMaxWidth().semantics(mergeDescendants = true) {}, verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
                BankLogo(bankOf(account), size = 44.dp)
                Column(Modifier.weight(1f)) {
                    Text(account.accountName ?: bankOf(account)?.name.orEmpty(), style = MaterialTheme.typography.titleSmall, color = Dincr.colors.text)
                    Caption(detail(account))
                }
            }
        }
    }
}

/** The success header's color (the hero's indigo). */
private val HomeHero = Color(0xFF2A2E6E)
