package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AuthException
import com.dincr.data.InvestmentChoice
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.generated.DincrSpacing
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/**
 * Plan → Tu plan del mes (VIP): whether investing is in the plan. Off until they turn it on. Turning it
 * on doesn't invest anything: a share appears only when debts and the Salvavidas allow it, and DINCR
 * never picks a stock. iOS: `InvestmentChoiceCard`.
 */
@Composable
fun InvestmentChoiceCard(model: AppModel, changed: () -> Unit) {
    var wanted by remember { mutableStateOf(false) }
    var loaded by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    val scope = rememberCoroutineScope()
    LaunchedEffect(Unit) {
        try { wanted = model.api.investmentChoice().wantsInvesting; loaded = true } catch (e: CancellationException) { throw e } catch (_: Exception) { }
    }
    DincrCard {
        Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(tx("Incluir inversiones en mi plan", "Include investing in my plan"), style = MaterialTheme.typography.titleSmall, color = Dincr.colors.text, modifier = Modifier.weight(1f))
                Switch(wanted, enabled = loaded, modifier = Modifier.testTag("plan.investmentChoice"), onCheckedChange = { value ->
                    val before = wanted
                    wanted = value
                    error = null
                    scope.launch {
                        model.load(tx("No pudimos guardar.", "We couldn’t save.")) { model.api.updateInvestmentChoice(InvestmentChoice(value)) }
                            .fold({ changed() }, { wanted = before; if (it !is AuthException.SignedOut) error = it.message })
                    }
                })
            }
            Caption(tx("Si lo activás, una parte irá a invertir solo cuando tus deudas y tu Salvavidas lo permitan. DINCR no elige acciones por vos.",
                "If you turn it on, a share goes to investing only when your debts and emergency fund allow it. DINCR doesn’t pick stocks for you."))
            error?.let { Text(it, color = Dincr.colors.negative, style = MaterialTheme.typography.bodySmall) }
        }
    }
}
