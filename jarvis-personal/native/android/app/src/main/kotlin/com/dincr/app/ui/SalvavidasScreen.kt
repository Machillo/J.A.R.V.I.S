package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.selection.toggleable
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Shield
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
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AuthException
import com.dincr.data.OpsFlag
import com.dincr.data.Salvavidas
import com.dincr.data.SalvavidasUpdate
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.EmptyState
import com.dincr.design.MoneyText
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal
import java.math.RoundingMode
import kotlinx.coroutines.launch

/**
 * Plan → Salvavidas (VIP; the Owner by role): `GET|PUT /user-product/vip/salvavidas`. The backend
 * answers the Users model (months of the user's own obligations, funded by the declared savings) or,
 * for the Owner role, the historical JARVIS model. Every figure is the backend's: no coverage math
 * on the device. Unknown savings show "Sin dato", never "0 meses".
 */
@Composable
fun SalvavidasScreen(model: AppModel, nav: Navigator) {
    val state = rememberLoad(model) { model.api.salvavidas() }
    val scope = rememberCoroutineScope()
    var saving by remember { mutableStateOf(false) }
    var editingAmount by remember { mutableStateOf(false) }

    fun update(update: SalvavidasUpdate, done: (String?) -> Unit = {}) {
        if (saving) return
        saving = true
        scope.launch {
            model.load(tx("No pudimos guardar el Salvavidas.", "We couldn’t save the emergency fund.")) { model.api.updateSalvavidas(update) }
                .onSuccess { state.replace(it); done(null) }
                .onFailure { if (it !is AuthException.SignedOut) { model.showNotice(it.message.orEmpty()); done(it.message) } }
            saving = false
        }
    }

    DetailScaffold(tx("Salvavidas", "Emergency fund"), nav::back) {
        if (!model.isOn(OpsFlag.VIP_INTELLIGENCE)) { FeaturePaused(model, OpsFlag.VIP_INTELLIGENCE); return@DetailScaffold }
        Caption(tx("Cuántos meses de tus obligaciones te cubre tu fondo de emergencia.", "How many months of your obligations your emergency fund covers."))
        LoadContent(state) { s ->
            if (!s.isOwnerScope && s.needsObligations) {
                EmptyState(Icons.Rounded.Shield, tx("Todavía no hay obligaciones", "No obligations yet"),
                    tx("El Salvavidas se mide con tus deudas y pagos recurrentes. Registralos para ver cuántos meses te cubre.", "The emergency fund is measured against your debts and recurring payments. Add them to see how many months it covers.")) {
                    DincrPrimaryButton(tx("Agregar pagos recurrentes", "Add recurring payments"), { nav.open("recurring") })
                }
                TextButton({ nav.open("debts") }, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp)) { Text(tx("Ver deudas", "See debts"), color = Dincr.colors.tint) }
                return@LoadContent
            }
            FundCard(s, onEdit = { editingAmount = true }, onSituation = { nav.open("incomeBase") })
            Section(tx("Objetivo", "Target")) {
                ChoiceChips(s.targetChoices.map { it to tx("$it ${if (it == 1) "mes" else "meses"}", "$it month${if (it == 1) "" else "s"}") }, s.targetMonths ?: 6,
                    { months -> if (months != s.targetMonths) update(SalvavidasUpdate.target(months)) })
                AmountLine(tx("Meta", "Target"), s.targetAmount, emphasize = true)
                AmountLine(tx("Base mensual", "Monthly base"), s.monthlyBase)
            }
            Section(tx("Qué protege", "What it protects")) {
                s.components?.let { c ->
                    AmountLine(tx("Cuotas de deudas", "Debt payments"), c.debtMonthlyPayments)
                    c.recurringObligations?.let { AmountLine(tx("Pagos recurrentes", "Recurring payments"), it) }
                    c.mandatoryFixedExpenses?.let { AmountLine(tx("Fijos obligatorios", "Mandatory fixed expenses"), it) }
                    c.protectedExpenses?.let { AmountLine(tx("Gastos protegidos", "Protected expenses"), it) }
                }
                s.debts.forEach { AmountLine("• ${it.name.orEmpty()}", it.monthlyPayment) }
                s.obligations.forEach { AmountLine("• ${it.name.orEmpty()}", it.monthlyAmount) }
                s.mandatoryExpenses.forEach { AmountLine("• ${it.name.orEmpty()}", it.monthlyAmount) }
            }
            if (s.isOwnerScope && s.availableExpenses.isNotEmpty()) ProtectedExpenses(s, saving) { ids -> update(SalvavidasUpdate.ownerProtected(ids)) }
            if (s.milestones.isNotEmpty()) Section(tx("Hitos", "Milestones")) {
                s.milestones.forEach { m ->
                    val reached = s.isAmountKnown && m.reached == true
                    AmountLine(tx("${m.months} ${if (m.months == 1) "mes" else "meses"}", "${m.months} month${if (m.months == 1) "" else "s"}") +
                        (if (reached) tx(" · alcanzado", " · reached") else ""), m.target)
                }
            }
            s.verification?.message?.let { Caption(it) }
        }
        FinancialDisclaimer()
    }
    if (editingAmount) {
        val owner = (state.state as? Load.Ready)?.value?.isOwnerScope == true
        AmountDialog(if (owner) tx("Saldo del Salvavidas", "Emergency fund balance") else tx("Actualizar ahorros", "Update savings"),
            if (owner) null else tx("Se guarda como tus ahorros disponibles de Ingresos y base.", "It’s saved as the available savings in Income and base."),
            tx("Guardar", "Save"), onDismiss = { editingAmount = false }) { amount, _ ->
            var error: String? = null
            model.load(tx("No pudimos guardar el Salvavidas.", "We couldn’t save the emergency fund.")) { model.api.updateSalvavidas(SalvavidasUpdate.amount(amount)) }
                .onSuccess { state.replace(it); editingAmount = false }
                .onFailure { if (it !is AuthException.SignedOut) error = it.message }
            error
        }
    }
}

/** The fund: amount and coverage when known; "Sin dato" and the way to declare it otherwise. */
@Composable
private fun FundCard(s: Salvavidas, onEdit: () -> Unit, onSituation: () -> Unit) {
    DincrCard {
        Column(Modifier.testTag("salvavidas.fund"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
            Text(tx("Tu fondo", "Your fund"), style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2)
            if (s.isAmountKnown) {
                MoneyText(s.currentAmount, style = MaterialTheme.typography.displaySmall)
                s.coverageMonths?.let { InfoLine(tx("Te cubre", "Covers you for"), monthsLabel(it)) }
                s.progressPercent?.let { ProgressLine(it / 100.0, tx("${it.toInt()} % de tu meta", "${it.toInt()} % of your target")) }
                s.missingAmount?.takeIf { it.signum() > 0 }?.let { AmountLine(tx("Te falta", "Still to go"), it) }
            } else {
                Text(tx("Sin dato", "No data"), style = MaterialTheme.typography.displaySmall, color = Dincr.colors.text)
                InfoLine(tx("Te cubre", "Covers you for"), tx("Sin dato", "No data"))
                Caption(tx("Declará tus ahorros para medir cuántos meses te cubre.", "Declare your savings to measure how many months it covers."))
                TextButton(onSituation, modifier = Modifier.heightIn(min = 48.dp)) { Text(tx("Completar ingresos y base", "Complete income and base"), color = Dincr.colors.tint) }
            }
            TextButton(onEdit, modifier = Modifier.heightIn(min = 48.dp)) {
                Text(if (s.isOwnerScope) tx("Editar saldo", "Edit balance") else tx("Actualizar ahorros", "Update savings"), color = Dincr.colors.tint)
            }
        }
    }
}

/** "2,5 meses": the backend's coverage, only rounded for display. */
private fun monthsLabel(months: BigDecimal): String {
    val shown = months.setScale(1, RoundingMode.HALF_UP).stripTrailingZeros().toPlainString().let { if (tx("es", "en") == "es") it.replace('.', ',') else it }
    return tx("$shown ${if (months.compareTo(BigDecimal.ONE) == 0) "mes" else "meses"}", "$shown month${if (months.compareTo(BigDecimal.ONE) == 0) "" else "s"}")
}

/** Owner: the optional expenses the fund protects (historical picker). */
@Composable
private fun ProtectedExpenses(s: Salvavidas, saving: Boolean, onChange: (List<Long>) -> Unit) {
    Section(tx("Gastos protegidos", "Protected expenses")) {
        s.availableExpenses.forEach { expense ->
            val id = expense.id ?: return@forEach
            val checked = expense.selected == true
            Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).toggleable(checked, enabled = !saving, role = Role.Checkbox) { on ->
                onChange(if (on) s.protectedExpenseIds + id else s.protectedExpenseIds - id)
            }, verticalAlignment = Alignment.CenterVertically) {
                Checkbox(checked, onCheckedChange = null)
                Text(expense.name.orEmpty(), style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text, modifier = Modifier.weight(1f))
                MoneyText(expense.monthlyAmount)
            }
        }
    }
}
