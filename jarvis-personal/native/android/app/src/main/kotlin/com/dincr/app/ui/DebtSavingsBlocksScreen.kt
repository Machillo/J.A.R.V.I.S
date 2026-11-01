package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AmountInput
import com.dincr.data.AuthException
import com.dincr.data.DebtSavingsBlockApply
import com.dincr.data.DebtSavingsBlockCreate
import com.dincr.data.DebtSavingsBlocks
import com.dincr.data.DebtSavingsReading
import com.dincr.data.OpsFlag
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.generated.DincrSpacing
import java.time.LocalDate
import kotlinx.coroutines.launch

/**
 * DB-1 — Plan → Ahorro para deudas (Owner only): the next locked savings block the strategy proposes
 * (which debt, how much every Thursday, for how long, what locking costs) and the blocks already
 * created at the bank, with their progress. The backend decides every number
 * (`GET /jarvis/premium/debt-savings-blocks`); "Ya lo creé en el banco" records a block (POST), "Quitar"
 * removes one (DELETE) and, when a block matures, "Ya lo aboné" records what was paid into the debt and
 * what the bank did (POST …/apply): all are the Owner's explicit actions. iOS twin:
 * `DebtSavingsBlocksView.swift`.
 */
@Composable
fun DebtSavingsBlocksScreen(model: AppModel, nav: Navigator) {
    val data = rememberLoad(model) { model.api.debtSavingsBlocks() }
    var notice by remember { mutableStateOf<String?>(null) }
    DetailScaffold(tx("Ahorro para deudas", "Savings for debts"), nav::back) {
        notice?.let { DincrCard { Text(it, color = Dincr.colors.text, modifier = Modifier.fillMaxWidth().testTag("debtBlocks.notice")) } }
        LoadContent(data) { state -> DebtSavingsBlocksContent(model, state, paid = { notice = it; data.reload() }) { data.reload() } }
    }
}

@Composable
private fun DebtSavingsBlocksContent(model: AppModel, state: DebtSavingsBlocks, paid: (String) -> Unit, changed: () -> Unit) {
    val format = Dincr.money
    val writes = model.isOn(OpsFlag.FINANCIAL_WRITES)
    var creating by remember(state) { mutableStateOf(false) }
    var removing by remember(state) { mutableStateOf<DebtSavingsBlocks.Block?>(null) }
    var paying by remember(state) { mutableStateOf<String?>(null) }
    var error by remember(state) { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()

    error?.let { com.dincr.design.ErrorState(it) }
    val proposal = state.proposal
    if (proposal != null) {
        Section(tx("Tu próximo ahorro", "Your next saving")) {
            Column(Modifier.fillMaxWidth().testTag("debtBlocks.proposal"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                Text(DebtSavingsReading.headline(proposal, format), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text,
                    modifier = Modifier.testTag("debtBlocks.headline"))
                DebtSavingsReading.lines(state, format).forEach { Text(it, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2) }
                Caption(DebtSavingsReading.recommendation(proposal))
                if (writes && !creating) {
                    DincrPrimaryButton(tx("Ya lo creé en el banco", "I created it at the bank"), modifier = Modifier.testTag("debtBlocks.create"), onClick = { creating = true })
                }
                if (creating) CreateBlockForm(model, proposal, onCancel = { creating = false }, onSaved = changed)
            }
        }
    } else {
        DebtSavingsReading.statusMessage(state)?.let { message ->
            DincrCard { Text(message, color = Dincr.colors.text, modifier = Modifier.fillMaxWidth().testTag("debtBlocks.status")) }
        }
    }
    DebtSavingsReading.warnings(state).forEach { Caption(it) }
    val blocks = state.blocks.orEmpty()
    if (blocks.isNotEmpty()) {
        Section(tx("Tus ahorros bloqueados", "Your locked savings")) {
            blocks.forEach { block ->
                Column(Modifier.fillMaxWidth().testTag("debtBlocks.block.${block.id}"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
                    Text(block.debtName ?: tx("Deuda", "Debt"), style = MaterialTheme.typography.titleSmall, color = Dincr.colors.text)
                    DebtSavingsReading.blockLines(block, format).forEach { Text(it, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2) }
                    if (writes && block.matured == true) {
                        if (paying == block.id) ApplyBlockForm(model, block, onCancel = { paying = null }, onPaid = paid)
                        else DincrPrimaryButton(tx("Ya lo aboné", "I paid it"), modifier = Modifier.testTag("debtBlocks.pay.${block.id}"), onClick = { paying = block.id })
                    }
                    if (writes) TextButton({ removing = block }, modifier = Modifier.heightIn(min = 48.dp).testTag("debtBlocks.remove.${block.id}")) {
                        Text(tx("Quitar", "Remove"), color = Dincr.colors.negative)
                    }
                }
            }
        }
    }
    removing?.let { block ->
        AlertDialog(
            onDismissRequest = { removing = null },
            title = { Text(tx("¿Quitar este ahorro?", "Remove this saving?")) },
            text = { Text(tx("Se quita de DINCR y tu plan deja de apartarlo. En el banco sigue como esté.",
                "It is removed from DINCR and your plan stops setting it aside. At the bank it stays as it is.")) },
            confirmButton = {
                TextButton({
                    removing = null
                    scope.launch {
                        model.load(tx("Intentalo de nuevo.", "Try again.")) { model.api.cancelDebtSavingsBlock(block.id) }
                            .onSuccess { changed() }
                            .onFailure { if (it !is AuthException.SignedOut) error = it.message }
                    }
                }, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Quitar", "Remove"), color = Dincr.colors.negative) }
            },
            dismissButton = { TextButton({ removing = null }, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Cancelar", "Cancel")) } },
        )
    }
}

/** What was created at the bank: prefilled with the proposal; the Owner corrects what the bank set. */
@Composable
private fun CreateBlockForm(model: AppModel, proposal: DebtSavingsBlocks.Proposal, onCancel: () -> Unit, onSaved: () -> Unit) {
    val format = Dincr.money
    var weekly by remember(proposal) { mutableStateOf(proposal.weeklyAmount?.let(format::inputText).orEmpty()) }
    var months by remember(proposal) { mutableStateOf(proposal.termMonths?.toString().orEmpty()) }
    var start by remember(proposal) {
        mutableStateOf(proposal.startDate?.take(10)?.let { runCatching { LocalDate.parse(it) }.getOrNull() } ?: LocalDate.now())
    }
    var error by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    MoneyField(tx("Cada jueves", "Every Thursday"), weekly, { weekly = it }, modifier = Modifier.testTag("debtBlocks.weekly"))
    FormField(tx("Meses (3 o más)", "Months (3 or more)"), months, { months = it }, keyboard = KeyboardType.Number, modifier = Modifier.testTag("debtBlocks.months"))
    DateField(tx("Primer ahorro", "First saving"), start, { picked -> picked?.let { start = it } })
    error?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Dincr.colors.negative) }
    DincrPrimaryButton(tx("Guardar", "Save"), loading = saving, modifier = Modifier.testTag("debtBlocks.save"), onClick = onClick@{
        val debtId = proposal.debt?.id ?: return@onClick
        val amount = AmountInput.parse(weekly, format.separators)?.takeIf { it.signum() > 0 }
            ?: run { error = tx("Escribí un monto mayor que cero.", "Enter an amount above zero."); return@onClick }
        val term = months.trim().toIntOrNull()?.takeIf { it in 3..60 }
            ?: run { error = tx("El plazo va de 3 a 60 meses.", "The term is 3 to 60 months."); return@onClick }
        saving = true; error = null
        scope.launch {
            model.load(tx("No pudimos guardar.", "We couldn’t save.")) {
                model.api.createDebtSavingsBlock(DebtSavingsBlockCreate(debtId, amount, start.toString(), term, proposal.mode))
            }
                .onSuccess { onSaved() }
                .onFailure { if (it !is AuthException.SignedOut) error = it.message }
            saving = false
        }
    })
    TextButton(onCancel, enabled = !saving, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Cancelar", "Cancel"), color = Dincr.colors.tint) }
}

/** The block matured and its money went into the debt: how much, and what the bank did with it. */
@Composable
private fun ApplyBlockForm(model: AppModel, block: DebtSavingsBlocks.Block, onCancel: () -> Unit, onPaid: (String) -> Unit) {
    val format = Dincr.money
    var amount by remember(block.id) { mutableStateOf(block.totalAtMaturity?.let(format::inputText).orEmpty()) }
    var outcome by remember(block.id) { mutableStateOf(DebtSavingsBlockApply.REDUCE_TERM) }
    var installment by remember(block.id) { mutableStateOf("") }
    var remaining by remember(block.id) { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var saving by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    MoneyField(tx("Cuánto abonaste", "How much you paid"), amount, { amount = it }, modifier = Modifier.testTag("debtBlocks.applyAmount"))
    ChoiceChips(listOf(DebtSavingsBlockApply.REDUCE_TERM to tx("Bajó el plazo", "Shortened the term"),
        DebtSavingsBlockApply.REDUCE_INSTALLMENT to tx("Bajó la cuota", "Lowered the installment")), outcome, { outcome = it }, tx("Qué hizo el banco", "What the bank did"))
    if (outcome == DebtSavingsBlockApply.REDUCE_TERM) {
        FormField(tx("Cuotas que te quedan", "Installments left"), remaining, { remaining = it }, keyboard = KeyboardType.Number,
            modifier = Modifier.testTag("debtBlocks.remaining"))
    }
    if (outcome == DebtSavingsBlockApply.REDUCE_INSTALLMENT) {
        MoneyField(tx("Cuota nueva", "New installment"), installment, { installment = it }, modifier = Modifier.testTag("debtBlocks.newInstallment"))
        Caption(tx("Lo que bajó la cuota se suma a tu siguiente ahorro.", "What the installment went down is added to your next saving."))
    }
    error?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Dincr.colors.negative) }
    DincrPrimaryButton(tx("Guardar", "Save"), loading = saving, modifier = Modifier.testTag("debtBlocks.applySave"), onClick = onClick@{
        val paid = AmountInput.parse(amount, format.separators)?.takeIf { it.signum() > 0 }
            ?: run { error = tx("Escribí un monto mayor que cero.", "Enter an amount above zero."); return@onClick }
        val newInstallment = if (outcome == DebtSavingsBlockApply.REDUCE_INSTALLMENT) {
            AmountInput.parse(installment, format.separators)?.takeIf { it.signum() > 0 }
                ?: run { error = tx("Escribí la cuota nueva.", "Enter the new installment."); return@onClick }
        } else null
        val left = if (outcome == DebtSavingsBlockApply.REDUCE_TERM) {
            remaining.trim().toIntOrNull()?.takeIf { it in 1..600 }
                ?: run { error = tx("Escribí cuántas cuotas te quedan.", "Enter how many installments are left."); return@onClick }
        } else null
        saving = true; error = null
        scope.launch {
            model.load(tx("No pudimos guardar.", "We couldn’t save.")) {
                model.api.applyDebtSavingsBlock(block.id, DebtSavingsBlockApply.of(paid, outcome, newInstallment, left))
            }
                .onSuccess { onPaid(DebtSavingsReading.appliedMessage(it.block.applied, format)) }
                .onFailure { if (it !is AuthException.SignedOut) error = it.message }
            saving = false
        }
    })
    TextButton(onCancel, enabled = !saving, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Cancelar", "Cancel"), color = Dincr.colors.tint) }
}
