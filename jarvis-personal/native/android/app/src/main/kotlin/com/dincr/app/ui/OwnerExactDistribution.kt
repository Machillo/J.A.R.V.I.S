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
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AmountInput
import com.dincr.data.AuthException
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

// Plan → Distribución de dinero, Owner only (phase 1). The MODE says where the money to split
// comes from (DINCR's estimate, or the amount the Owner has left after paying everything, split
// whole: no obligation is deducted from it again); the STRATEGY (the backend's
// Director engine) decides how it is split, the same in both. The exact amount is a plan: the
// backend writes and stores nothing (POST /jarvis/premium/strategy-dashboard/exact-distribution,
// refused to anyone but the Owner).

enum class DistributionMode { ESTIMATE, EXACT }

/** The backend's ceiling for a confirmed amount (backend/ai/models.py EXACT_DISTRIBUTION_MAX). */
val EXACT_DISTRIBUTION_MAX = BigDecimal("1000000000")

@Composable
fun OwnerDistributionModes(model: AppModel, estimate: DirectorStrategy, nav: Navigator) {
    var mode by rememberSaveable { mutableStateOf(DistributionMode.ESTIMATE) }
    // Amount, result and error together: editing the amount drops a result calculated from another.
    var form by remember { mutableStateOf(ExactDistributionForm()) }
    var loading by remember { mutableStateOf(false) }
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
            Caption(tx("Indicá cuánto dinero te sobra después de pagar tus gastos, tarjetas y cuotas. DINCR reparte ese monto completo con tu estrategia actual, sin volver a descontar esos pagos. No registra movimientos ni cambia tus saldos.",
                "Enter how much money you have left after paying your expenses, cards and instalments. DINCR splits that whole amount with your current strategy, without deducting those payments again. It records no movement and changes no balance."))
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
                            }.onSuccess { form = form.calculated(typed, it.strategy) }
                                .onFailure { if (it !is AuthException.SignedOut && form.amountText == typed) form = form.failed(it.message) }
                            loading = false
                        }
                    }
                }
            }, modifier = Modifier.fillMaxWidth().testTag("exact-distribution-calculate"), loading = loading)
            form.result?.let { ExactResult(it, nav) }
        }
    }
}

@Composable
private fun ExactResult(strategy: DirectorStrategy, nav: Navigator) {
    StatusBanner(BannerTone.INFO, tx("Calculado con el monto que indicaste", "Calculated from the amount you entered"),
        tx("Es un plan: no se registró ningún movimiento ni cambió ningún saldo.", "It’s a plan: no movement was recorded and no balance changed."))
    strategy.distributionWarnings.forEach { warning ->
        DincrMessage(MessageKind.ATTENTION, tx("Dato incompleto", "Incomplete data"), warning.message.orEmpty())
    }
    DirectorDistribution(strategy, nav)
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
