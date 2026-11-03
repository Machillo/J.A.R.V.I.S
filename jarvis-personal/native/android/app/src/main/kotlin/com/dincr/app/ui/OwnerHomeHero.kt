package com.dincr.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Add
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dincr.app.tx
import com.dincr.data.AppLanguage
import com.dincr.data.HomeStatus
import com.dincr.data.MoneyFormat
import com.dincr.design.Dincr
import com.dincr.design.TabularNums
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal

/** The solid top of the Owner's Hoy, with its text: one color in both schemes (iOS `OwnerColor.hero`). */
internal val OwnerHeroColor = Color(0xFF1B2BD6)
private val OnHero = Color.White
private val OnHero2 = Color(0xFFDDE1FF)
private val HeroControl = Color(0xFF3545E6)

/**
 * The top of the Owner's Hoy: greeting, the day's key figure and the main actions on one solid color.
 * Read-only figures: the same [HomeStatus] the blocks below use, and unknown stays "—" (the block below
 * says what DINCR needs). iOS: `OwnerHomeHero`.
 */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun OwnerHomeHero(greeting: String, name: String, status: HomeStatus?, cycle: String?, onExpense: () -> Unit, onIncome: () -> Unit, onJarvis: () -> Unit, modifier: Modifier = Modifier) {
    Column(modifier.background(OwnerHeroColor).padding(horizontal = DincrSpacing.s4, vertical = DincrSpacing.s4), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s4)) {
        Column(Modifier.testTag("owner.home.greeting").semantics(mergeDescendants = true) { heading() }) {
            Text(greeting, style = MaterialTheme.typography.bodyLarge, color = OnHero2)
            if (name.isNotEmpty()) Text("$name.", style = MaterialTheme.typography.headlineMedium.copy(fontWeight = FontWeight.Bold), color = OnHero)
        }
        status?.let { Figure(it, cycle) }
        // Wraps instead of squeezing a label on a narrow screen or at a large text size.
        FlowRow(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s2), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
            HeroAction(tx("Gasto", "Expense"), tx("Registrar gasto", "Record expense"), Icons.Rounded.Add, prominent = true, tag = "owner.home.addExpense", onClick = onExpense)
            HeroAction(tx("Ingreso", "Income"), tx("Registrar ingreso", "Record income"), Icons.Rounded.Add, prominent = false, tag = "owner.home.addIncome", onClick = onIncome)
            // The one way into JARVIS from Hoy (spec OW-1).
            HeroAction("JARVIS", "JARVIS", Icons.Rounded.AutoAwesome, prominent = false, tag = "owner.home.jarvis", onClick = onJarvis)
        }
    }
}

@OptIn(ExperimentalLayoutApi::class)
@Composable
private fun Figure(status: HomeStatus, cycle: String?) {
    Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
        Text(
            if (status.headline == HomeStatus.Headline.SAFE_TO_SPEND) tx("Podés gastar con tranquilidad", "Safe to spend") else tx("Resultado del mes", "This month’s result"),
            style = MaterialTheme.typography.labelLarge, color = OnHero2,
        )
        HeroAmount(status.amount, MoneyFormat.Sign.NONE, big = true, modifier = Modifier.testTag("home.status.amount"))
        cycle?.let { Text(it, Modifier.testTag("home.status.cycle"), style = MaterialTheme.typography.bodySmall, color = OnHero2) }
    }
    FlowRow(Modifier.fillMaxWidth().testTag("home.status.facts"), horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s4), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
        HeroFact(tx("Ingresos", "Income"), status.income, MoneyFormat.Sign.INCOME, tx("Sin registrar", "Not recorded"))
        HeroFact(tx("Gastos", "Expenses"), status.expenses, MoneyFormat.Sign.EXPENSE, tx("Sin registrar", "Not recorded"))
        if (status.headline == HomeStatus.Headline.SAFE_TO_SPEND) {
            HeroFact(if (status.cycle == null) tx("Resultado del mes", "Month result") else tx("Resultado del corte", "Statement result"), status.result, MoneyFormat.Sign.NONE, "—")
        }
    }
}

@Composable
private fun HeroFact(label: String, amount: BigDecimal?, sign: MoneyFormat.Sign, unknown: String) {
    Column(Modifier.semantics(mergeDescendants = true) {}) {
        Text(label, style = MaterialTheme.typography.bodySmall, color = OnHero2)
        if (amount != null) HeroAmount(amount, sign, big = false)
        else Text(unknown, style = MaterialTheme.typography.labelLarge, color = OnHero2)
    }
}

/** `MoneyText`'s text and spoken label on the hero's color. */
@Composable
private fun HeroAmount(amount: BigDecimal?, sign: MoneyFormat.Sign, big: Boolean, modifier: Modifier = Modifier) {
    val format = Dincr.money
    val spoken = amount?.let { format.spoken(it, sign) } ?: AppLanguage.current().pick("sin dato", "no data")
    Text(
        amount?.let { format.format(it, sign) } ?: "—",
        modifier.semantics { contentDescription = spoken },
        style = (if (big) MaterialTheme.typography.displaySmall.copy(fontWeight = FontWeight.Bold, fontSize = 40.sp) else MaterialTheme.typography.labelLarge).merge(TabularNums),
        color = OnHero, maxLines = 1,
    )
}

@Composable
private fun HeroAction(label: String, spokenLabel: String, icon: ImageVector, prominent: Boolean, tag: String, onClick: () -> Unit) {
    Box(Modifier.testTag(tag)) {
        Row(
            Modifier.heightIn(min = 48.dp).clip(CircleShape).background(if (prominent) OnHero else HeroControl)
                .clickable(onClickLabel = spokenLabel, role = Role.Button, onClick = onClick)
                .semantics(mergeDescendants = true) { contentDescription = spokenLabel }
                .padding(horizontal = DincrSpacing.s4),
            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s1),
        ) {
            Icon(icon, contentDescription = null, tint = if (prominent) OwnerHeroColor else OnHero, modifier = Modifier.size(18.dp))
            Text(label, style = MaterialTheme.typography.labelLarge, color = if (prominent) OwnerHeroColor else OnHero)
        }
    }
}
