package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CreditCard
import androidx.compose.material.icons.rounded.Flag
import androidx.compose.material.icons.rounded.Inbox
import androidx.compose.material.icons.rounded.PersonOutline
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.BasicDashboard
import com.dincr.data.Budget
import com.dincr.data.AttentionList
import com.dincr.data.CommandCenter
import com.dincr.data.FinancialCalendar
import com.dincr.data.FinancialSituation
import com.dincr.data.FreeDashboard
import com.dincr.data.MessageKind
import com.dincr.data.MoneyFormat
import com.dincr.data.OpsFlag
import com.dincr.data.PlanTier
import com.dincr.design.CategoryBars
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.DincrMessage
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.EmptyState
import com.dincr.design.IncomeExpenseBars
import com.dincr.design.MoneyText
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal
import java.time.LocalDate

sealed interface Load<out T> { data object Loading : Load<Nothing>; data class Failed(val message: String) : Load<Nothing>; data class Ready<T>(val value: T) : Load<T> }

/** PARITY C1/C2/C3 — Today, per plan. Every figure is a backend value. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(model: AppModel, padding: PaddingValues, nav: Navigator) {
    val profile by model.profile.collectAsStateWithLifecycle()
    val flags by model.flags.collectAsStateWithLifecycle()
    val plan = profile?.planTier ?: PlanTier.FREE
    val vipLive = plan == PlanTier.VIP && flags.isEnabled(OpsFlag.VIP_INTELLIGENCE)
    LaunchedEffect(Unit) { model.recordScreen("dashboard_opened", "home") }
    val home = rememberLoad(model, plan, vipLive, fallback = tx("No pudimos cargar tu resumen.", "We couldn’t load your overview.")) {
        when {
            vipLive -> HomeData.Vip(model.api.commandCenter())
            plan != PlanTier.FREE -> HomeData.Basic(model.api.basicDashboard(),
                runCatching { model.api.budget() }.getOrNull(), runCatching { model.api.calendar(LocalDate.now().toString().take(7)) }.getOrNull())
            else -> HomeData.Free(model.api.freeDashboard())
        }
    }
    val situation = rememberLoad(model) { model.api.financialSituation() }
    PullToRefreshBox(home.state is Load.Loading && false, onRefresh = { home.reload(); situation.reload() }, modifier = Modifier.fillMaxSize().padding(padding)) {
        ScreenColumn {
            Text(tx("Hola, ${profile?.firstName.orEmpty()}", "Hi, ${profile?.firstName.orEmpty()}"), style = MaterialTheme.typography.headlineMedium,
                color = Dincr.colors.text, modifier = Modifier.padding(top = DincrSpacing.s2).semantics { heading() })
            if (profile?.isCourtesy == true) Caption(tx("Tenés ${profile?.subscription?.planName ?: plan.name} de cortesía.", "You have ${profile?.subscription?.planName ?: plan.name} as a courtesy."))
            LoadContent(home, rows = 3) { data ->
                when (data) {
                    is HomeData.Free -> FreeHome(data.dashboard, nav)
                    is HomeData.Basic -> BasicHome(data, nav)
                    is HomeData.Vip -> VipHome(data.center, flags.isEnabled(OpsFlag.GMAIL_AUTOMATION), nav)
                }
            }
            YourFinances(nav)
            (situation.state as? Load.Ready)?.value?.let { ProfileNudge(it, nav) }
        }
    }
}

/** Debts and goals (all plans) live in Hoy; the screens themselves are unchanged. */
@Composable
private fun YourFinances(nav: Navigator) {
    DincrCard {
        Column {
            NavRow(Icons.Rounded.CreditCard, tx("Deudas", "Debts"), tx("Saldos, cuotas y pagos", "Balances, payments")) { nav.open("debts") }
            NavRow(Icons.Rounded.Flag, tx("Metas y ahorros", "Goals and savings"), tx("Metas y planes de ahorro", "Goals and savings plans")) { nav.open("goals") }
        }
    }
}

private sealed interface HomeData {
    data class Free(val dashboard: FreeDashboard) : HomeData
    data class Basic(val dashboard: BasicDashboard, val budget: Budget?, val calendar: FinancialCalendar?) : HomeData
    data class Vip(val center: CommandCenter) : HomeData
}

@Composable
private fun FreeHome(d: FreeDashboard, nav: Navigator) {
    KeyFigure(tx("Disponible este mes", "Available this month"), d.available, d.income, d.expenses, d.debtBalance)
    // Presentation only: the backend always sends six months, zero-filled for new accounts.
    val empty = d.categories.isEmpty() && d.income.signum() == 0 && d.expenses.signum() == 0 &&
        d.monthlyHistory.all { it.income.signum() == 0 && it.expenses.signum() == 0 }
    if (empty) {
        EmptyState(Icons.Rounded.Inbox, tx("Todavía no hay movimientos", "No transactions yet"),
            tx("Cuando registrés ingresos y gastos, acá verás tu mes y en qué se va el dinero.", "When you record income and expenses, you’ll see your month and where the money goes here.")) {
            DincrPrimaryButton(tx("Agregar movimiento", "Add transaction"), { nav.tab(Destination.MOVEMENTS) })
        }
    } else {
        Section(tx("Ingresos y gastos", "Income and expenses")) { IncomeExpenseBars(d.monthlyHistory.map { Triple(shortMonth(it.month), it.income, it.expenses) }) }
        Section(tx("En qué se va el dinero", "Where the money goes")) { CategoryBars(d.categories.map { it.category to it.amount }) }
        TextButton({ nav.open("monthly") }, modifier = Modifier.fillMaxWidth()) { Text(tx("Ver resumen del mes", "See monthly summary"), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.tint) }
    }
}

@Composable
private fun BasicHome(data: HomeData.Basic, nav: Navigator) {
    val d = data.dashboard
    KeyFigure(tx("Balance del mes", "Month balance"), d.balance, d.income, d.expenses, d.debt?.remaining)
    // The backend's six months (zero-filled), as on iOS (PlanDashboards); nothing summed on the device.
    if (d.monthlyHistory.isNotEmpty()) Section(tx("Ingresos y gastos", "Income and expenses")) {
        IncomeExpenseBars(d.monthlyHistory.map { Triple(shortMonth(it.month), it.income, it.expenses) })
    }
    data.budget?.let { budget ->
        val spent = budget.items.sumOf { it.spent ?: BigDecimal.ZERO }
        Section(tx("Presupuesto", "Budget")) {
            AmountLine(tx("Gastado", "Spent"), spent)
            AmountLine(tx("Presupuestado", "Budgeted"), budget.totalBudgeted)
            percentOf(spent, budget.totalBudgeted)?.let { ProgressLine(it, tx("${(it * 100).toInt()} % usado", "${(it * 100).toInt()} % used")) }
            TextButton({ nav.open("budget") }) { Text(tx("Ver presupuesto", "See budget"), color = Dincr.colors.tint) }
        }
    }
    data.calendar?.let { calendar ->
        val today = LocalDate.now()
        val upcoming = calendar.events.filter { e -> e.date?.let { runCatching { LocalDate.parse(it) }.getOrNull() }?.let { !it.isBefore(today) && !it.isAfter(today.plusDays(7)) } == true }
        Section(tx("Próximos 7 días", "Next 7 days")) {
            if (upcoming.isEmpty()) Caption(tx("No tenés pagos conocidos esta semana.", "No known payments this week."))
            upcoming.take(4).forEach { AmountLine("${dateLabel(it.date)} · ${it.name.orEmpty()}", it.amount) }
            TextButton({ nav.open("calendar") }) { Text(tx("Ver calendario", "See calendar"), color = Dincr.colors.tint) }
        }
    }
    d.goals?.let { goals ->
        Section(tx("Metas", "Goals")) {
            AmountLine(tx("Ahorrado", "Saved"), goals.current)
            percentOf(goals.current, goals.target)?.let { ProgressLine(it, tx("${(it * 100).toInt()} % de tus metas", "${(it * 100).toInt()} % of your goals")) }
        }
    }
    if (d.categories.isNotEmpty()) Section(tx("En qué se va el dinero", "Where the money goes")) {
        CategoryBars(d.categories.map { (it.category ?: tx("Sin categoría", "Uncategorized")) to (it.amount ?: BigDecimal.ZERO) })
    }
}

@Composable
private fun VipHome(c: CommandCenter, mailReviewAvailable: Boolean, nav: Navigator) {
    DincrCard {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
            Text(tx("Podés gastar con tranquilidad", "Safe to spend"), style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2)
            MoneyText(c.safeToSpend?.amount, style = MaterialTheme.typography.displaySmall)
            c.safeToSpend?.next45DaysMinimum?.let { AmountLine(tx("Saldo mínimo previsto (45 días)", "Lowest expected balance (45 days)"), it) }
        }
    }
    c.director?.let { d ->
        Section(tx("Tu prioridad", "Your priority")) {
            d.headline?.let { Text(it, style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text) }
            d.nextAction?.let { Text(it, style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text2) }
            if (d.dataComplete == false) TextButton({ nav.open("situation") }) { Text(tx("Completar mi situación", "Complete my situation"), color = Dincr.colors.tint) }
        }
    }
    // UX-5: alerts and pending mail notices, ordered and deduplicated; left out when there are none.
    AttentionSection(AttentionList.today(c, mailReviewAvailable), nav)
    if (c.roadmap.isNotEmpty()) Section(tx("Tu plan de acción", "Your action plan")) {
        c.roadmap.sortedBy { it.order ?: Int.MAX_VALUE }.take(3).forEach { step ->
            Column(Modifier.padding(vertical = DincrSpacing.s1)) {
                AmountLine("${step.order ?: ""}. ${step.title.orEmpty()}", step.amount?.takeIf { it.signum() > 0 })
                step.why?.let { Caption(it) }
            }
        }
    }
    c.projections.firstOrNull { it.months == 6 }?.let { p ->
        Section(tx("En 6 meses", "In 6 months")) {
            AmountLine(tx("Patrimonio neto", "Net worth"), p.netWorth, emphasize = true)
            AmountLine(tx("Deuda", "Debt"), p.debt)
            TextButton({ nav.open("projections") }) { Text(tx("Ver proyecciones", "See projections"), color = Dincr.colors.tint) }
        }
    }
}

@Composable
private fun KeyFigure(label: String, available: BigDecimal?, income: BigDecimal?, expenses: BigDecimal?, debt: BigDecimal?) {
    DincrCard {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
            Text(label, style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2)
            MoneyText(available, style = MaterialTheme.typography.displaySmall)
            Row(Modifier.padding(top = DincrSpacing.s2), horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s6)) {
                Figure(tx("Ingresos", "Income"), income, MoneyFormat.Sign.INCOME)
                Figure(tx("Gastos", "Expenses"), expenses, MoneyFormat.Sign.EXPENSE)
            }
            debt?.takeIf { it.signum() > 0 }?.let {
                HorizontalDivider(color = Dincr.colors.line, modifier = Modifier.padding(vertical = DincrSpacing.s1))
                AmountLine(tx("Deuda pendiente", "Outstanding debt"), it)
            }
        }
    }
}

@Composable
private fun Figure(label: String, amount: BigDecimal?, sign: MoneyFormat.Sign) {
    Column(Modifier.semantics(mergeDescendants = true) {}) {
        Text(label, style = MaterialTheme.typography.bodySmall, color = Dincr.colors.textMuted)
        MoneyText(amount, sign = sign)
    }
}

@Composable
fun Section(title: String, content: @Composable () -> Unit) {
    DincrCard {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
            Text(title, style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text, modifier = Modifier.semantics { heading() })
            content()
        }
    }
}

/** B10 — one missing piece of the declared situation at a time (read only; never guessed). */
@Composable
private fun ProfileNudge(situation: FinancialSituation, nav: Navigator) {
    val profile = situation.profile
    val prompt = when {
        profile?.incomeType == null -> tx("Contanos cómo recibís tus ingresos para calcular mejor tu mes.", "Tell us how you get paid to plan your month better.")
        profile.essentialMonthlyExpenses == null -> tx("Indicá tus gastos esenciales del mes.", "Add your essential monthly expenses.")
        (situation.debts?.missingInterest ?: 0) > 0 -> tx("Algunas deudas no tienen tasa de interés.", "Some debts have no interest rate.")
        else -> null
    } ?: return
    DincrCard {
        Row(verticalAlignment = androidx.compose.ui.Alignment.CenterVertically) {
            RoundedIcon(Icons.Rounded.PersonOutline)
            Column(Modifier.weight(1f).padding(horizontal = DincrSpacing.s3)) {
                Text(prompt, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text)
                TextButton({ nav.open(if (prompt.contains("tasa") || prompt.contains("interest")) "debts" else "situation") }) { Text(tx("Completar", "Complete"), color = Dincr.colors.tint) }
            }
        }
    }
}

fun shortMonth(period: String): String {
    val month = period.substringAfter('-').toIntOrNull() ?: return period
    val names = if (tx("es", "en") == "es") listOf("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic")
    else listOf("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    return names.getOrElse(month - 1) { period }
}
