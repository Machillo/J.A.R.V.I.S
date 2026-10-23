package com.dincr.app.ui

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.Saver
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AmountInput
import com.dincr.data.AuthException
import com.dincr.data.ConfirmationPlan
import com.dincr.data.DirectorStrategy
import com.dincr.data.ExactDistributionForm
import com.dincr.data.ExactDistributionRequest
import com.dincr.data.MessageKind
import com.dincr.design.BannerTone
import com.dincr.design.Dincr
import com.dincr.design.DincrMessage
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.StatusBanner
import java.math.BigDecimal
import kotlinx.coroutines.launch

// Plan → Distribución de dinero, Owner only. The MODE says where the money to split comes from
// (DINCR's estimate, or the amount the Owner has left after paying everything, split whole: no
// obligation is deducted from it again); the STRATEGY (the backend's Director engine) decides how
// it is split, the same in both. Calculating an exact amount is a plan: the backend writes nothing
// (POST /jarvis/premium/strategy-dashboard/exact-distribution). CONFIRMAR is the Owner declaring he
// carried it out: the backend records the debt payments, the Salvavidas deposit and the other
// destinations once (POST .../exact-distribution/confirm). Both are refused to anyone but the Owner.

enum class DistributionMode { ESTIMATE, EXACT }

private val FormSaver = Saver<ExactDistributionForm, String>(save = { it.saved() }, restore = { ExactDistributionForm.restored(it) })

/** The backend's ceiling for a confirmed amount (backend/ai/models.py EXACT_DISTRIBUTION_MAX). */
val EXACT_DISTRIBUTION_MAX = BigDecimal("1000000000")

@Composable
fun OwnerDistributionModes(model: AppModel, estimate: DirectorStrategy, nav: Navigator, onRecorded: suspend () -> Unit = {}) {
    var mode by rememberSaveable { mutableStateOf(DistributionMode.ESTIMATE) }
    // Amount, result and error together: editing the amount drops a result calculated from another.
    // Saved across a rotation or a killed process, so a result keeps its confirmation key: pressing
    // CONFIRMAR again after an interrupted confirmation never records it twice.
    var form by rememberSaveable(stateSaver = FormSaver) { mutableStateOf(ExactDistributionForm()) }
    var loading by remember { mutableStateOf(false) }
    var confirming by remember { mutableStateOf(false) }
    var asking by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val format = Dincr.money
    ModeSelector(mode) { mode = it }
    when (mode) {
        DistributionMode.ESTIMATE -> {
            StatusBanner(BannerTone.INFO, tx("Distribución aproximada", "Estimated distribution"),
                tx("Calculada con tus registros en DINCR. Puede diferir del dinero que realmente tenés.",
                    "Calculated from your records in DINCR. It may differ from the money you really have."))
            DirectorDistribution(estimate, nav)
        }
        DistributionMode.EXACT -> {
            Caption(tx("Indicá cuánto dinero te sobra después de pagar tus gastos, tarjetas y cuotas. DINCR reparte ese monto completo con tu estrategia actual, sin volver a descontar esos pagos. Calcular no registra nada: solo CONFIRMAR registra los movimientos.",
                "Enter how much money you have left after paying your expenses, cards and instalments. DINCR splits that whole amount with your current strategy, without deducting those payments again. Calculating records nothing: only CONFIRM records the movements."))
            MoneyField(tx("Monto que te sobra, en colones", "Amount you have left, in colones"), form.amountText,
                { form = form.edited(it) }, form.error, symbol = "₡", modifier = Modifier.testTag("exact-distribution-amount"))
            DincrPrimaryButton(if (form.result == null) tx("Calcular distribución", "Calculate distribution") else tx("Actualizar distribución", "Update distribution"), {
                val typed = form.amountText
                val amount = AmountInput.parse(typed, format.separators)
                when {
                    amount == null -> form = form.failed(tx("Escribí un monto mayor que cero, con hasta dos decimales.", "Enter an amount above zero, with up to two decimals."))
                    amount > EXACT_DISTRIBUTION_MAX -> form = form.failed(tx("El monto no puede superar ₡1.000.000.000.", "The amount can’t exceed ₡1,000,000,000."))
                    else -> {
                        loading = true
                        scope.launch {
                            model.load(tx("No pudimos calcular la distribución.", "We couldn’t calculate the distribution.")) {
                                model.api.ownerExactDistribution(ExactDistributionRequest(amount))
                            }.onSuccess { form = form.calculated(typed, it.strategy, it.confirmationPlan) }
                                .onFailure { if (it !is AuthException.SignedOut && form.amountText == typed) form = form.failed(it.message) }
                            loading = false
                        }
                    }
                }
            }, modifier = Modifier.fillMaxWidth().testTag("exact-distribution-calculate"), loading = loading, enabled = !confirming)
            form.result?.let { ExactResult(form, it, nav) }
            if (form.canConfirm) {
                DincrPrimaryButton(tx("CONFIRMAR", "CONFIRM"), { asking = true },
                    modifier = Modifier.fillMaxWidth().testTag("exact-distribution-confirm"), loading = confirming)
            }
        }
    }
    if (asking) ConfirmDialog(
        tx("¿Ya hiciste estos movimientos?", "Did you already make these movements?"),
        tx("Al confirmar, DINCR registra los abonos, el ahorro y los demás destinos de esta distribución, y tus saldos cambian. Confirmá solo si ya moviste el dinero así.",
            "When you confirm, DINCR records the payments, the savings and the other destinations of this distribution, and your balances change. Confirm only if you already moved the money this way."),
        tx("Confirmar", "Confirm"), destructive = false, busy = confirming,
        onConfirm = {
            val key = form.confirmationKey
            val request = AmountInput.parse(form.amountText, format.separators)?.let { form.confirmRequest(it) }
            if (key == null || request == null) {
                asking = false
            } else {
                confirming = true
                scope.launch {
                    model.load(tx("No pudimos saber si se registró. Volvé a presionar CONFIRMAR: si ya se registró, no se repite.", "We couldn’t tell whether it was recorded. Press CONFIRM again: if it was already recorded, it isn’t repeated.")) {
                        model.api.ownerConfirmExactDistribution(request)
                    }.onSuccess { form = form.confirmed(key, it); onRecorded() }
                        .onFailure { if (it !is AuthException.SignedOut) form = form.failed(it.message) }
                    confirming = false
                    asking = false
                }
            }
        },
        onDismiss = { asking = false },
    )
}

@Composable
private fun ExactResult(form: ExactDistributionForm, strategy: DirectorStrategy, nav: Navigator) {
    if (form.confirmation != null) {
        DincrMessage(MessageKind.POSITIVE, tx("Distribución confirmada", "Distribution confirmed"),
            tx("Se registraron los abonos, el ahorro y los demás destinos. Tus deudas, tu Salvavidas y tu estrategia ya lo reflejan.",
                "The payments, the savings and the other destinations were recorded. Your debts, Salvavidas and strategy already show it."))
    } else {
        StatusBanner(BannerTone.INFO, tx("Calculado con el monto que indicaste", "Calculated from the amount you entered"),
            tx("Todavía no se registró nada. Si ya moviste el dinero así, presioná CONFIRMAR.", "Nothing has been recorded yet. If you already moved the money this way, press CONFIRM."))
    }
    strategy.distributionWarnings.forEach { warning ->
        DincrMessage(MessageKind.ATTENTION, tx("Dato incompleto", "Incomplete data"), warning.message.orEmpty())
    }
    DirectorDistribution(strategy, nav)
    form.plan?.let { plan ->
        Section(if (form.confirmation != null) tx("Lo que se registró", "What was recorded") else tx("Lo que se registrará al confirmar", "What CONFIRM will record")) {
            plan.steps.forEach { step -> ConfirmationStepLines(step) }
        }
        plan.blockingReasons.forEach { DincrMessage(MessageKind.ATTENTION, tx("No se puede confirmar", "It can’t be confirmed"), it) }
    }
}

@Composable
private fun ConfirmationStepLines(step: ConfirmationPlan.Step) {
    when (step.action) {
        "debt_extra_payment" -> step.targets.forEach { AmountLine(tx("Abono a ${it.name.orEmpty()}", "Payment to ${it.name.orEmpty()}"), it.amount) }
        "salvavidas_deposit" -> AmountLine(tx("Depósito al Salvavidas", "Deposit to the Salvavidas"), step.amount)
        "goal_contribution" -> AmountLine(tx("Aporte a ${step.goalName.orEmpty()}", "Contribution to ${step.goalName.orEmpty()}"), step.amount)
        "investment_reserve" -> AmountLine(tx("Reservado para invertir", "Reserved to invest"), step.amount)
        else -> AmountLine(tx("Para vivir (no se registra: tus gastos se registran cuando ocurren)", "To live on (not recorded: spending is recorded when it happens)"), step.amount)
    }
}

@Composable
private fun ModeSelector(mode: DistributionMode, onSelect: (DistributionMode) -> Unit) {
    val options = listOf(DistributionMode.ESTIMATE to tx("Aproximada", "Estimated"), DistributionMode.EXACT to tx("Monto exacto", "Exact amount"))
    SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth().testTag("distribution-mode")) {
        options.forEachIndexed { index, (value, label) ->
            SegmentedButton(mode == value, { onSelect(value) }, SegmentedButtonDefaults.itemShape(index, options.size)) { Text(label) }
        }
    }
}
