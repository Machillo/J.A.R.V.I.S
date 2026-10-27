package com.dincr.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.KeyboardArrowRight
import androidx.compose.material.icons.rounded.AttachMoney
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import com.dincr.app.tx
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.AppModel
import com.dincr.data.PendingConversion
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.TabularNums
import com.dincr.design.generated.DincrSpacing
import kotlinx.coroutines.CancellationException

/**
 * Hoy: the dollars waiting for the close, beside the colones figures ("US$150,50 por convertir").
 * They are not in the month's colones totals until the close converts them with one rate, so Hoy says
 * how much is waiting instead of hiding it or counting it as ₡0. Shown only when there is something
 * waiting; read-only. Tap: Movimientos, where each one is listed. iOS: `PendingDollarsCard`.
 */
@Composable
fun PendingDollarsCard(model: AppModel, onOpen: () -> Unit) {
    var pending by remember { mutableStateOf(PendingConversion.UNAVAILABLE) }
    val generation by model.dataGeneration.collectAsStateWithLifecycle()
    LaunchedEffect(generation) {
        // Optional: Hoy never fails because of it; on error it simply stays out.
        pending = try { model.api.pendingConversion() } catch (e: CancellationException) { throw e } catch (_: Exception) { pending }
    }
    if (pending.totals.isEmpty()) return
    DincrCard(Modifier.clickable(onClick = onOpen).testTag("home.pendingDollars").semantics(mergeDescendants = true) {}) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Rounded.AttachMoney, contentDescription = null, tint = Dincr.colors.tint, modifier = Modifier.size(28.dp))
            Spacer(Modifier.width(DincrSpacing.s3))
            Column(Modifier.weight(1f)) {
                Text(tx("Por convertir al cierre", "To convert at the close"), style = MaterialTheme.typography.bodySmall, color = Dincr.colors.textMuted)
                pending.totals.forEach { total ->
                    val amount = Dincr.money.copy(currency = total.currency).format(total.amount)
                    Text(if (total.count == 1) tx("$amount · 1 gasto", "$amount · 1 expense") else tx("$amount · ${total.count} gastos", "$amount · ${total.count} expenses"),
                        style = MaterialTheme.typography.titleSmall.merge(TabularNums), color = Dincr.colors.text)
                }
            }
            Icon(Icons.AutoMirrored.Rounded.KeyboardArrowRight, contentDescription = null, tint = Dincr.colors.textMuted)
        }
    }
}
