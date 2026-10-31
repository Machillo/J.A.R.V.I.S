package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.Wealth
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.MoneyText
import com.dincr.design.generated.DincrSpacing

/**
 * WE-2 — Patrimonio neto (VIP and the Owner): the figure, or what is missing to know it, then what
 * you have and what you owe (`/vip/wealth`). An unknown part is named, never drawn as 0. iOS twin:
 * `NetWorthCard` in `AdvisorViews.swift`.
 */
@Composable
fun NetWorthCard(model: AppModel) {
    val data = rememberLoad(model) { model.api.wealth() }
    DincrCard {
        Column(Modifier.fillMaxWidth().testTag("wealth.netWorth"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
            LoadContent(data) { wealth ->
                Text(tx("Patrimonio neto", "Net worth"), style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2)
                val net = wealth.netWorth
                if (net != null) {
                    Column(Modifier.testTag("wealth.netWorth.amount")) { MoneyText(net, style = MaterialTheme.typography.headlineMedium) }
                    Text(if (net.signum() < 0) tx("Hoy debés más de lo que tenés.", "Today you owe more than you have.")
                        else tx("Es lo que te quedaría si vendieras todo y pagaras todas tus deudas.", "It is what you would keep if you sold everything and paid every debt."),
                        style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2)
                } else {
                    wealth.missingNotice()?.let {
                        Text(it, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2, modifier = Modifier.testTag("wealth.netWorth.missing"))
                    }
                }
                WealthGroup(tx("Lo que tenés", "What you have"), wealth.assets?.total, wealth.owned, "wealth.assets")
                WealthGroup(tx("Lo que debés", "What you owe"), wealth.liabilities?.total, wealth.owed(), "wealth.liabilities")
            }
        }
    }
}

@Composable
private fun WealthGroup(title: String, total: java.math.BigDecimal?, items: List<Wealth.Item>, tag: String) {
    Column(Modifier.testTag(tag), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
        AmountLine(title, total, emphasize = true)
        if (items.isEmpty()) Caption(tx("Nada registrado.", "Nothing recorded."))
        items.forEach { AmountLine(it.name ?: tx("Sin nombre", "Unnamed"), it.amount) }
    }
}
