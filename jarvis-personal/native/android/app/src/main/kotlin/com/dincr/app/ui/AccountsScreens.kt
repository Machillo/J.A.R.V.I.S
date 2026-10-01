package com.dincr.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.KeyboardArrowRight
import androidx.compose.material.icons.rounded.AccountBalance
import androidx.compose.material.icons.rounded.MarkEmailRead
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
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.LifecycleResumeEffect
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.Accounts
import com.dincr.data.AuthException
import com.dincr.data.FinancialIdentity
import com.dincr.data.MailCandidate
import com.dincr.data.OpsFlag
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.EmptyState
import com.dincr.design.generated.DincrSpacing
import kotlinx.coroutines.launch

/**
 * Cuentas (VIP + mail automation; the Owner by role): the second surface of the SAME review system
 * as Email Monitor. Banks → bank (its detected accounts and its movements) → account (its
 * movements). Movements are the same candidates with the same actions and states; both surfaces
 * reload from the backend whenever they appear, so a review in one shows in the other. No balance
 * is ever shown (a detected account's balance is unknown) and no full account number.
 */
private data class AccountsData(val identity: FinancialIdentity, val candidates: List<MailCandidate>) {
    val groups: List<Accounts.BankGroup> get() = Accounts.group(identity.items, candidates)
}

private suspend fun loadAccounts(model: AppModel) = AccountsData(model.api.financialIdentity(), model.api.mailCandidates(pendingOnly = false))

/** Cuentas needs mail automation and VIP intelligence (`/vip/financial-identity` pauses with both). */
@Composable
private fun accountsPaused(model: AppModel): Boolean {
    val paused = listOf(OpsFlag.GMAIL_AUTOMATION, OpsFlag.VIP_INTELLIGENCE).firstOrNull { !model.isOn(it) } ?: return false
    FeaturePaused(model, paused)
    return true
}

fun bankGroupName(group: Accounts.BankGroup): String = group.bank?.name ?: tx("Otras instituciones", "Other institutions")

fun ownershipLabel(status: String?): String = when (status) {
    "own" -> tx("Tuya", "Yours"); "not_mine" -> tx("No es tuya", "Not yours"); else -> tx("Sin confirmar", "Unconfirmed")
}

@Composable
fun AccountsScreen(model: AppModel, nav: Navigator) {
    val data = rememberLoad(model) { loadAccounts(model) }
    LifecycleResumeEffect(Unit) { data.reload(); onPauseOrDispose { } }
    DetailScaffold(tx("Cuentas", "Accounts"), nav::back) {
        if (accountsPaused(model)) return@DetailScaffold
        Caption(tx("Tus bancos según los avisos que DINCR leyó. DINCR no muestra saldos ni números de cuenta completos.",
            "Your banks from the notices DINCR read. DINCR shows no balances or full account numbers."))
        LoadContent(data) { d ->
            val groups = d.groups
            if (groups.isEmpty()) EmptyState(Icons.Rounded.AccountBalance, tx("Sin cuentas detectadas", "No accounts detected"),
                tx("Las cuentas aparecen cuando DINCR procesa avisos de tu banco.", "Accounts appear when DINCR processes notices from your bank."))
            groups.forEach { group ->
                DincrCard {
                    Row(Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable { nav.push("accounts/bank/${group.key}") }.semantics(mergeDescendants = true) {},
                        verticalAlignment = Alignment.CenterVertically) {
                        BankLogo(group.bank)
                        Column(Modifier.weight(1f).padding(horizontal = DincrSpacing.s3)) {
                            Text(bankGroupName(group), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
                            Caption(listOf(
                                tx("${group.accounts.size} ${if (group.accounts.size == 1) "cuenta" else "cuentas"}", "${group.accounts.size} account${if (group.accounts.size == 1) "" else "s"}"),
                                tx("${group.movements} movimientos", "${group.movements} transactions"),
                                tx("${group.pending} por revisar", "${group.pending} to review"),
                            ).joinToString(" · "))
                        }
                        Icon(Icons.AutoMirrored.Rounded.KeyboardArrowRight, contentDescription = null, tint = Dincr.colors.textMuted)
                    }
                }
            }
        }
    }
}

/** One bank: its detected accounts (with the ownership action) and its movements (`emails?bank=`). */
@Composable
fun BankAccountsScreen(model: AppModel, nav: Navigator, key: String?) {
    val data = rememberLoad(model, key) {
        val base = loadAccounts(model)
        val group = base.groups.firstOrNull { it.key == key }
        // The same review inbox, filtered by the bank names the candidates carry.
        val movements = group?.bankQueries?.map { model.api.mailCandidates(bank = it) }?.let(Accounts::merge).orEmpty()
        Triple(base, group, movements)
    }
    LifecycleResumeEffect(Unit) { data.reload(); onPauseOrDispose { } }
    val reviewer = rememberCandidateReviewer(model) { data.reload() }
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf<Long?>(null) }
    val title = (data.state as? Load.Ready)?.value?.second?.let(::bankGroupName) ?: tx("Cuentas", "Accounts")
    DetailScaffold(title, nav::back) {
        if (accountsPaused(model)) return@DetailScaffold
        LoadContent(data) { (_, group, movements) ->
            if (group == null) {
                EmptyState(Icons.Rounded.AccountBalance, tx("Sin datos de este banco", "No data for this bank"), tx("Volvé a Cuentas para ver tus bancos.", "Go back to Accounts to see your banks."))
                return@LoadContent
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                BankLogo(group.bank, size = 48.dp)
                Text(bankGroupName(group), style = MaterialTheme.typography.titleLarge, color = Dincr.colors.text, modifier = Modifier.padding(start = DincrSpacing.s3))
            }
            SectionTitle(tx("Cuentas", "Accounts"))
            if (group.accounts.isEmpty()) Caption(tx("Todavía no hay cuentas detectadas de este banco.", "No accounts detected for this bank yet."))
            group.accounts.forEach { account ->
                AccountCard(account, busy = busy != null, onOpen = { nav.push("accounts/account/${account.id}") }) { own ->
                    busy = account.id
                    scope.launch {
                        model.load(tx("No pudimos guardarlo.", "We couldn’t save it.")) { model.api.setAccountOwnership(account.id, own) }
                            .onFailure { if (it !is AuthException.SignedOut) model.showNotice(it.message.orEmpty()) }
                        busy = null; data.reload()
                    }
                }
            }
            SectionTitle(tx("Movimientos", "Transactions"))
            MovementList(movements, reviewer)
        }
    }
    CandidateCorrectionHost(reviewer)
}

/** One detected account and its movements (`emails?financial_account_id=`). */
@Composable
fun AccountMovementsScreen(model: AppModel, nav: Navigator, id: Long?) {
    val data = rememberLoad(model, id) {
        val account = model.api.financialIdentity().items.firstOrNull { it.id == id }
        account to (if (account != null) model.api.mailCandidates(financialAccountId = account.id) else emptyList())
    }
    LifecycleResumeEffect(Unit) { data.reload(); onPauseOrDispose { } }
    val reviewer = rememberCandidateReviewer(model) { data.reload() }
    DetailScaffold(tx("Movimientos de la cuenta", "Account transactions"), nav::back) {
        if (accountsPaused(model)) return@DetailScaffold
        LoadContent(data) { (account, movements) ->
            if (account == null) {
                EmptyState(Icons.Rounded.AccountBalance, tx("Cuenta no encontrada", "Account not found"), tx("Volvé a Cuentas para ver tus bancos.", "Go back to Accounts to see your banks."))
                return@LoadContent
            }
            val bank = com.dincr.data.BankBranding.describe(account.institutionCode, account.bankName)
            Row(verticalAlignment = Alignment.CenterVertically) {
                BankLogo(bank)
                Column(Modifier.padding(start = DincrSpacing.s3)) {
                    Text(listOfNotNull(account.bankName, account.accountName).joinToString(" · "), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
                    Caption(listOfNotNull(Accounts.maskedLabel(account), account.currency, ownershipLabel(account.ownershipStatus)).joinToString(" · "))
                }
            }
            MovementList(movements, reviewer)
        }
    }
    CandidateCorrectionHost(reviewer)
}

@Composable
private fun AccountCard(account: FinancialIdentity.Account, busy: Boolean, onOpen: () -> Unit, onOwnership: (Boolean) -> Unit) {
    DincrCard {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable(onClick = onOpen), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(account.accountName ?: tx("Cuenta", "Account"), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
                    Caption(listOfNotNull(Accounts.maskedLabel(account), account.currency, ownershipLabel(account.ownershipStatus)).joinToString(" · "))
                }
                Icon(Icons.AutoMirrored.Rounded.KeyboardArrowRight, contentDescription = tx("Ver movimientos", "See transactions"), tint = Dincr.colors.textMuted)
            }
            Row {
                listOf(true to tx("Es mía", "It’s mine"), false to tx("No es mía", "Not mine")).forEach { (own, label) ->
                    TextButton(enabled = !busy, onClick = { onOwnership(own) }, modifier = Modifier.heightIn(min = 48.dp)) { Text(label, color = Dincr.colors.tint) }
                }
            }
        }
    }
}

@Composable
private fun MovementList(movements: List<MailCandidate>, reviewer: CandidateReviewer) {
    if (movements.isEmpty()) EmptyState(Icons.Rounded.MarkEmailRead, tx("Sin movimientos", "No transactions"),
        tx("Los avisos de este banco aparecen acá y en Correos financieros.", "This bank’s notices appear here and in Financial emails."))
    movements.forEach { candidate -> CandidateRow(candidate, reviewer) }
}
