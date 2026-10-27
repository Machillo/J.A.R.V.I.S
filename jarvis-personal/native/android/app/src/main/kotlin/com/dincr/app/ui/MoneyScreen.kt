package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.selection.toggleable
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.AccountBalance
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
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
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AccountBalanceRequest
import com.dincr.data.AccountBalances
import com.dincr.data.AmountInput
import com.dincr.data.AuthException
import com.dincr.data.CycleReport
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.EmptyState
import com.dincr.design.MoneyText
import com.dincr.design.generated.DincrSpacing
import kotlinx.coroutines.launch

/**
 * JARVIS → Mi dinero (Owner only): the current cycle (expected and received income, the statement
 * period's spending, debt payments, goal reserves and the real balance) and the Owner's accounts with
 * their balances. Opening it only reads; saving or removing an account is an explicit Owner command.
 * The cycle and the accounts load independently: one failing never hides the other. Every amount is
 * the backend's. iOS: `MoneyView`.
 */
@Composable
fun MoneyScreen(model: AppModel, nav: Navigator) {
    val cycle = rememberLoad(model, fallback = tx("No pudimos cargar tu ciclo.", "We couldn’t load your cycle.")) { model.api.cycleReport() }
    val accounts = rememberLoad(model, fallback = tx("No pudimos cargar tus cuentas.", "We couldn’t load your accounts.")) { model.api.accountBalances() }
    var form by remember { mutableStateOf<AccountForm?>(null) }
    var removing by remember { mutableStateOf<AccountBalances.Account?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    DetailScaffold(tx("Mi dinero", "My money"), nav::back, actions = {
        IconButton({ form = AccountForm(null) }, modifier = Modifier.heightIn(min = 48.dp).testTag("money.add")) {
            Icon(Icons.Rounded.Add, contentDescription = tx("Nueva cuenta", "New account"))
        }
    }) {
        LoadContent(cycle) { CycleCard(it) }
        LoadContent(accounts) { data -> AccountsContent(data, update = { form = AccountForm(it) }, remove = { removing = it }) }
    }
    form?.let { open ->
        AccountFormDialog(model, open.existing, onDismiss = { form = null }) {
            form = null; accounts.reload(); model.showNotice(tx("Cuenta guardada", "Account saved"))
        }
    }
    removing?.let { account ->
        ConfirmDialog(tx("¿Quitar «${account.accountName.orEmpty()}» de tus cuentas?", "Remove “${account.accountName.orEmpty()}” from your accounts?"),
            tx("Deja de sumar en tu dinero. Sus movimientos no se borran.", "It stops counting in your money. Its movements aren’t deleted."),
            tx("Quitar", "Remove"), busy = busy, onDismiss = { removing = null }, onConfirm = {
                val id = account.accountId ?: return@ConfirmDialog
                busy = true
                scope.launch {
                    model.load(tx("No pudimos quitarla. Revisá tus cuentas antes de intentar de nuevo.", "We couldn’t remove it. Check your accounts before trying again.")) {
                        model.api.removeAccountBalance(id)
                    }.fold(
                        { accounts.reload(); model.showNotice(tx("Cuenta quitada", "Account removed")) },
                        { if (it !is AuthException.SignedOut) model.showNotice(it.message.orEmpty()) })
                    busy = false
                    removing = null
                }
            })
    }
}

/** The open account form: a new account ([existing] null), or a new balance for [existing]. */
private data class AccountForm(val existing: AccountBalances.Account?)

/** "Tu ciclo": the income cycle and the statement period, as the backend computed them. */
@Composable
private fun CycleCard(report: CycleReport) {
    DincrCard(Modifier.testTag("money.cycle")) {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
            Caption(tx("Tu ciclo", "Your cycle"))
            val start = report.cycle?.start
            val end = report.cycle?.end
            if (start != null && end != null) Caption(tx("Ciclo: ${dateLabel(start)} – ${dateLabel(end)}", "Cycle: ${dateLabel(start)} – ${dateLabel(end)}"))
            val statementStart = report.expenseCycle?.start
            val statementEnd = report.expenseCycle?.end
            if (statementStart != null && statementEnd != null) {
                Caption(tx("Estado de cuenta: ${dateLabel(statementStart)} – ${dateLabel(statementEnd)}", "Statement: ${dateLabel(statementStart)} – ${dateLabel(statementEnd)}"))
            }
            AmountLine(tx("Ingresos esperados", "Expected income"), report.income?.expectedTotal)
            AmountLine(tx("Ingresos recibidos", "Income received"), report.income?.receivedFromTransactions)
            report.income?.pendingProjection?.takeIf { it.signum() > 0 }?.let { AmountLine(tx("Por recibir", "Still to come"), it) }
            AmountLine(tx("Gastos del período", "Spending this period"), report.expenses?.spendingOnly)
            AmountLine(tx("Pagos de deudas", "Debt payments"), report.expenses?.debtPayments)
            report.goals?.reservedCurrentPeriod?.takeIf { it.signum() > 0 }?.let { AmountLine(tx("Reservado para metas", "Set aside for goals"), it) }
            AmountLine(tx("Saldo real", "Real balance"), report.cashflow?.realBalance, emphasize = true)
        }
    }
}

/** "Tus cuentas": the total that counts and one card per account. */
@Composable
private fun AccountsContent(balances: AccountBalances, update: (AccountBalances.Account) -> Unit, remove: (AccountBalances.Account) -> Unit) {
    DincrCard(Modifier.testTag("money.accounts")) {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
            Caption(tx("Tus cuentas", "Your accounts"))
            AmountLine(tx("Total", "Total"), balances.totalRealBalance, currency = balances.currency)
        }
    }
    if (balances.items.isEmpty()) {
        EmptyState(Icons.Rounded.AccountBalance, tx("Sin cuentas", "No accounts"),
            tx("Con «+» agregás una cuenta y su saldo.", "Use “+” to add an account and its balance."))
    }
    balances.items.forEach { account ->
        DincrCard(Modifier.testTag("money.account.${account.id}")) {
            Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text(listOfNotNull(account.accountName ?: tx("Cuenta", "Account"), account.accountLast4?.let { "••$it" }).joinToString(" "),
                            style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
                        account.bankName?.takeIf { it.isNotBlank() }?.let { Caption(it) }
                    }
                    MoneyText(account.balance, currency = account.currency)
                }
                account.balanceAsOf?.let { Caption(tx("Al ${dateLabel(it)}", "As of ${dateLabel(it)}")) }
                if (!account.includeInNetWorth) Caption(tx("No suma a tu patrimonio", "Doesn’t count toward your net worth"))
                if (account.isEditable) Row(horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                    TextButton({ update(account) }, modifier = Modifier.heightIn(min = 48.dp).testTag("money.edit.${account.id}")) {
                        Text(tx("Actualizar saldo", "Update balance"), color = Dincr.colors.tint)
                    }
                    TextButton({ remove(account) }, modifier = Modifier.heightIn(min = 48.dp).testTag("money.delete.${account.id}")) {
                        Text(tx("Quitar", "Remove"), color = Dincr.colors.negative)
                    }
                }
            }
        }
    }
}

private fun typeLabel(type: String): String = when (type) {
    "checking" -> tx("Cuenta corriente", "Checking")
    "savings" -> tx("Ahorro", "Savings")
    "credit_card" -> tx("Tarjeta de crédito", "Credit card")
    "cash" -> tx("Efectivo", "Cash")
    else -> tx("Otra", "Other")
}

/**
 * "Nueva cuenta" / "Actualizar saldo": the account and the balance the Owner checked. An update keeps
 * the account's name and last 4 digits (they identify it) and leaves the balance empty, so the Owner
 * writes the one checked today instead of confirming a figure DINCR calculated. Sent once: disabled
 * while it is sent, never retried on its own.
 */
@Composable
private fun AccountFormDialog(model: AppModel, existing: AccountBalances.Account?, onDismiss: () -> Unit, onSaved: () -> Unit) {
    var name by remember { mutableStateOf(existing?.accountName.orEmpty()) }
    var bank by remember { mutableStateOf(existing?.bankName.orEmpty()) }
    var last4 by remember { mutableStateOf(existing?.accountLast4.orEmpty()) }
    var balance by remember { mutableStateOf("") }
    var currency by remember { mutableStateOf(existing?.currency?.uppercase()?.takeIf { it in AccountBalanceRequest.currencies } ?: "CRC") }
    var type by remember { mutableStateOf(existing?.accountType?.takeIf { it in AccountBalanceRequest.accountTypes } ?: "checking") }
    var includeInNetWorth by remember { mutableStateOf(existing?.includeInNetWorth ?: true) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val separators = Dincr.money.separators
    val example = amountExample()
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text(if (existing == null) tx("Nueva cuenta", "New account") else tx("Actualizar saldo", "Update balance")) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                if (existing == null) {
                    FormField(tx("Nombre de la cuenta", "Account name"), name, { name = it; error = null }, modifier = Modifier.testTag("money.form.name"))
                } else {
                    Text(listOfNotNull(name, existing.accountLast4?.let { "••$it" }).joinToString(" "), style = MaterialTheme.typography.titleMedium,
                        color = Dincr.colors.text, modifier = Modifier.testTag("money.form.name"))
                }
                FormField(tx("Banco (opcional)", "Bank (optional)"), bank, { bank = it }, modifier = Modifier.testTag("money.form.bank"))
                if (existing == null) {
                    FormField(tx("Últimos 4 dígitos (opcional)", "Last 4 digits (optional)"), last4, { last4 = it; error = null },
                        keyboard = KeyboardType.Number, modifier = Modifier.testTag("money.form.last4"))
                }
                MoneyField(tx("Saldo de hoy", "Today’s balance"), balance, { balance = it; error = null }, symbol = Dincr.money.copy(currency = currency).symbol,
                    modifier = Modifier.testTag("money.form.balance"))
                val shown = existing?.let { account -> account.balance?.let { Dincr.money.format(it, currencyOverride = account.currency) } }
                shown?.let { Caption(tx("Saldo que DINCR muestra: $it", "Balance DINCR shows: $it")) }
                ChoiceChips(AccountBalanceRequest.currencies.map { it to it }, currency, { currency = it }, tx("Moneda", "Currency"))
                ChoiceChips(AccountBalanceRequest.accountTypes.map { it to typeLabel(it) }, type, { type = it }, tx("Tipo", "Type"))
                Row(Modifier.fillMaxWidth().toggleable(includeInNetWorth, role = Role.Switch) { includeInNetWorth = it }.heightIn(min = 48.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Text(tx("Suma a mi patrimonio", "Counts toward my net worth"), Modifier.weight(1f), color = Dincr.colors.text)
                    Switch(includeInNetWorth, onCheckedChange = null)
                }
                error?.let { Text(it, color = Dincr.colors.negative, style = MaterialTheme.typography.bodySmall) }
            }
        },
        confirmButton = {
            TextButton(enabled = !busy, modifier = Modifier.testTag("money.form.save"), onClick = {
                val accountName = name.trim()
                val digits = last4.trim()
                // The balance is never guessed: an empty or invalid field is not sent. 0 is a real balance.
                val value = AmountInput.parseZeroOrMore(balance, separators)
                when {
                    accountName.isEmpty() -> error = tx("Escribí el nombre de la cuenta.", "Enter the account name.")
                    !AccountBalanceRequest.isValidLast4(digits) -> error = tx("Los últimos dígitos son 4 números, o dejalo vacío.", "The last digits are 4 numbers, or leave it empty.")
                    value == null -> error = tx("Escribí el saldo, por ejemplo $example.", "Enter the balance, for example $example.")
                    else -> {
                        busy = true
                        scope.launch {
                            model.load(tx("No pudimos guardarla. Revisá tus cuentas antes de intentar de nuevo.", "We couldn’t save it. Check your accounts before trying again.")) {
                                model.api.saveAccountBalance(AccountBalanceRequest(accountName, value, bank.trim(), digits, currency, type, includeInNetWorth))
                            }.fold({ onSaved() }, { if (it !is AuthException.SignedOut) error = it.message })
                            busy = false
                        }
                    }
                }
            }) { Text(tx("Guardar", "Save")) }
        },
        dismissButton = { TextButton(onDismiss, enabled = !busy) { Text(tx("Cancelar", "Cancel")) } },
    )
}
