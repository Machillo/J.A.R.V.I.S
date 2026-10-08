package com.dincr.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.rounded.ReceiptLong
import androidx.compose.material.icons.rounded.AddCircleOutline
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.CalendarMonth
import androidx.compose.material.icons.rounded.CreditCard
import androidx.compose.material.icons.rounded.Flag
import androidx.compose.material.icons.rounded.Forum
import androidx.compose.material.icons.rounded.GridView
import androidx.compose.material.icons.rounded.HelpOutline
import androidx.compose.material.icons.rounded.SouthWest
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.HomeDestination
import com.dincr.data.HomeInput
import com.dincr.data.HomeNext
import com.dincr.data.HomeShortcut
import com.dincr.data.HomeStatus
import com.dincr.data.HomeToday
import com.dincr.data.JarvisEvent
import com.dincr.data.MonthPlan
import com.dincr.data.MoneyFormat
import com.dincr.data.MovementKind
import com.dincr.data.OpsFlag
import com.dincr.data.OwnerHome
import com.dincr.data.PlanTier
import com.dincr.data.TrendMeaning
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.DincrProgressBar
import com.dincr.design.MoneyText
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal
import java.time.LocalTime
import java.time.YearMonth
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope

sealed interface Load<out T> { data object Loading : Load<Nothing>; data class Failed(val message: String) : Load<Nothing>; data class Ready<T>(val value: T) : Load<T> }

/**
 * Hoy (UX-6). The public plans get four blocks — Estado de hoy, Para atender, Qué sigue, Accesos
 * rápidos — from [HomeToday]; the plan decides what each block knows (Free facts, Basic + budget and
 * commitments, VIP + safe to spend and the director). The Owner (server role, never a plan) gets its
 * JARVIS space first, then the same blocks. Read-only: opening Hoy never writes. iOS: `HomeView`.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun HomeScreen(model: AppModel, padding: PaddingValues, nav: Navigator) {
    val profile by model.profile.collectAsStateWithLifecycle()
    val flags by model.flags.collectAsStateWithLifecycle()
    val owner = profile?.isOwner == true
    val plan = profile?.planTier ?: PlanTier.FREE
    // VIP intelligence is VIP while `vip_intelligence` is on; otherwise VIP reads as Basic (as before).
    val tier = when {
        plan == PlanTier.VIP && flags.isEnabled(OpsFlag.VIP_INTELLIGENCE) -> HomeToday.Tier.VIP
        plan != PlanTier.FREE -> HomeToday.Tier.BASIC
        else -> HomeToday.Tier.FREE
    }
    val mailReview = flags.isEnabled(OpsFlag.GMAIL_AUTOMATION)
    LaunchedEffect(Unit) { model.recordScreen("dashboard_opened", "home") }
    val home = rememberLoad(model, tier, mailReview, fallback = tx("No pudimos cargar tu resumen.", "We couldn’t load your overview.")) {
        loadHomeToday(model, tier, mailReview)
    }
    val agenda = if (owner) rememberLoad(model, fallback = tx("No pudimos cargar tu agenda.", "We couldn’t load your calendar.")) { model.api.jarvisUpcomingEvents() } else null
    PullToRefreshBox(false, onRefresh = { home.reload(); agenda?.reload() }, modifier = Modifier.fillMaxSize().padding(padding)) {
        ScreenColumn {
            if (owner && agenda != null) {
                OwnerJarvisSpace(profile?.firstName.orEmpty(), agenda, nav)
            } else {
                Text(tx("Hola, ${profile?.firstName.orEmpty()}", "Hi, ${profile?.firstName.orEmpty()}"), style = MaterialTheme.typography.headlineMedium,
                    color = Dincr.colors.text, modifier = Modifier.padding(top = DincrSpacing.s2).semantics { heading() })
            }
            Column(Modifier.testTag(if (owner) "owner.home" else "home.today"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s4)) {
                LoadContent(home, rows = 3) { today -> HomeBlocks(model, today, nav, onSaved = home.reload) }
            }
        }
    }
}

/**
 * Reads what Hoy needs for a plan. The plan's main source is required (its failure is the screen's
 * error); the extras (debts, budget, calendar, strategy) are optional and simply left out when they
 * can't be read. GETs only.
 */
private suspend fun loadHomeToday(model: AppModel, tier: HomeToday.Tier, mailReview: Boolean): HomeToday = coroutineScope {
    val api = model.api
    val debts = async { runCatching { api.debts() }.getOrNull() }
    when (tier) {
        HomeToday.Tier.FREE -> HomeToday.free(api.freeDashboard(), debts.await())
        HomeToday.Tier.BASIC -> {
            val budget = async { runCatching { api.budget() }.getOrNull() }
            val calendar = async { runCatching { api.calendar(YearMonth.now().toString()) }.getOrNull() }
            val strategy = async { runCatching { api.strategyBasic() }.getOrNull() }
            HomeToday.basic(api.basicDashboard(), budget.await(), calendar.await(), strategy.await()?.let(MonthPlan::of), debts.await())
        }
        HomeToday.Tier.VIP -> {
            val budget = async { runCatching { api.budget() }.getOrNull() }
            val calendar = async { runCatching { api.calendar(YearMonth.now().toString()) }.getOrNull() }
            HomeToday.vip(api.commandCenter(), budget.await(), calendar.await(), debts.await(), mailReview)
        }
    }
}

// MARK: 0. The Owner's JARVIS space (first, as it historically was)

@Composable
private fun OwnerJarvisSpace(name: String, agenda: LoadHandle<List<JarvisEvent>>, nav: Navigator) {
    val greeting = when (OwnerHome.greeting(LocalTime.now().hour)) {
        OwnerHome.Greeting.MORNING -> tx("Buenos días,", "Good morning,")
        OwnerHome.Greeting.AFTERNOON -> tx("Buenas tardes,", "Good afternoon,")
        OwnerHome.Greeting.EVENING -> tx("Buenas noches,", "Good evening,")
    }
    Column(Modifier.padding(top = DincrSpacing.s2).testTag("owner.home.greeting").semantics(mergeDescendants = true) { heading() }) {
        Text(greeting, style = MaterialTheme.typography.titleLarge, color = Dincr.colors.text2)
        if (name.isNotEmpty()) Text("$name.", style = MaterialTheme.typography.headlineMedium, color = Dincr.colors.text)
    }
    SectionTitle("JARVIS")
    DincrCard {
        Column {
            Box(Modifier.testTag("owner.home.jarvis.chat")) {
                NavRow(Icons.Rounded.Forum, tx("Chat", "Chat"), tx("Horas extra, VGH, feriados, bonos y tu agenda", "Overtime, VGH, holidays, bonuses and your calendar")) { nav.push("jarvis/chat") }
            }
            Box(Modifier.testTag("owner.home.jarvis.agenda")) {
                NavRow(Icons.Rounded.CalendarMonth, tx("Agenda", "Calendar"), tx("Tus eventos y recordatorios", "Your events and reminders")) { nav.push("jarvis/calendar") }
            }
            Box(Modifier.testTag("owner.home.jarvis.hub")) {
                NavRow(Icons.Rounded.GridView, tx("Todo JARVIS", "All of JARVIS"), tx("Tu espacio personal", "Your personal space")) { nav.open("jarvis") }
            }
        }
    }
    SectionTitle(tx("Próximos", "Coming up"))
    LoadContent(agenda, rows = 2) { events ->
        val next = OwnerHome.upcoming(events)
        DincrCard {
            Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                if (next.isEmpty()) {
                    Box(Modifier.testTag("owner.home.agenda.empty")) {
                        NavRow(Icons.Rounded.CalendarMonth, tx("Sin compromisos próximos", "No upcoming commitments"), tx("Agendá con JARVIS", "Schedule with JARVIS")) { nav.push("jarvis/chat") }
                    }
                }
                next.forEach { event ->
                    Row(Modifier.fillMaxWidth().testTag("owner.home.agenda.event").semantics(mergeDescendants = true) {}, horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
                        Column(Modifier.width(88.dp)) {
                            Caption(dateLabel(event.day))
                            Text(event.time ?: tx("Todo el día", "All day"), style = MaterialTheme.typography.labelLarge, color = Dincr.colors.tint)
                        }
                        Text(event.title, style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text)
                    }
                }
                TextButton({ nav.push("jarvis/calendar") }) { Text(tx("Ver agenda", "See calendar"), color = Dincr.colors.tint) }
            }
        }
    }
}

// MARK: The four blocks

@Composable
private fun HomeBlocks(model: AppModel, home: HomeToday, nav: Navigator, onSaved: () -> Unit) {
    var editor by remember { mutableStateOf<MovementKind?>(null) }
    val open: (HomeDestination) -> Unit = { destination ->
        when (destination) {
            HomeDestination.REGISTER_INCOME -> editor = MovementKind.INCOME
            HomeDestination.REGISTER_MOVEMENT -> editor = MovementKind.EXPENSE
            HomeDestination.MOVEMENTS -> nav.tab(Destination.MOVEMENTS)
            else -> destination.route?.let(nav::open)
        }
    }
    HomeStatusCard(home.status, open)
    home.attention?.let { AttentionSection(it, nav) }
    HomeNextCard(home.next, open)
    HomeShortcuts(home.shortcuts, open)
    editor?.let { kind ->
        MovementEditorSheet(model, EditorMode.Create, onDismiss = { editor = null }, onSaved = { editor = null; onSaved() }, onDelete = {}, initialKind = kind)
    }
}

// 1. Estado de hoy

@Composable
private fun HomeStatusCard(status: HomeStatus, open: (HomeDestination) -> Unit) {
    var explains by remember { mutableStateOf(false) }
    Column(Modifier.testTag("home.status"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
        SectionTitle(tx("Estado de hoy", "Today’s status"))
        DincrCard {
            Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
                Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
                    Text(
                        when (status.headline) {
                            HomeStatus.Headline.MONTH_RESULT -> tx("Resultado del mes", "This month’s result")
                            HomeStatus.Headline.SAFE_TO_SPEND -> tx("Podés gastar con tranquilidad", "Safe to spend")
                        },
                        style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2,
                    )
                    if (status.amount != null) {
                        MoneyText(status.amount, modifier = Modifier.testTag("home.status.amount"), style = MaterialTheme.typography.displaySmall)
                    } else {
                        // Unknown, never ₡0: what DINCR can't calculate yet, and on "?" why and how to give it.
                        Row(Modifier.testTag("home.status.unknown"), verticalAlignment = Alignment.CenterVertically) {
                            Text("—", style = MaterialTheme.typography.displaySmall, color = Dincr.colors.text2, modifier = Modifier.clearAndSetSemantics {})
                            Text(tx("Aún no puedo calcularlo", "I can’t calculate this yet"), style = MaterialTheme.typography.bodyMedium,
                                color = Dincr.colors.text2, modifier = Modifier.weight(1f).padding(start = DincrSpacing.s2))
                            val helpLabel = tx("Qué necesita DINCR", "What DINCR needs")
                            IconButton({ explains = !explains }, Modifier.testTag("home.status.help").semantics { contentDescription = helpLabel }) {
                                Icon(Icons.Rounded.HelpOutline, contentDescription = null, tint = Dincr.colors.tint)
                            }
                        }
                        if (explains) MissingInputs(status.missing, "home.status", open)
                    }
                    if (status.headline == HomeStatus.Headline.SAFE_TO_SPEND) {
                        Row(Modifier.semantics(mergeDescendants = true) {}, horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s1), verticalAlignment = Alignment.CenterVertically) {
                            Caption(tx("Libre después de compromisos", "Left after commitments"))
                            if (status.margin != null) MoneyText(status.margin, style = MaterialTheme.typography.bodySmall) else Caption("—")
                        }
                    }
                    status.lowestBalance?.let { lowest ->
                        Row(Modifier.semantics(mergeDescendants = true) {}, horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s1), verticalAlignment = Alignment.CenterVertically) {
                            Caption(tx("Saldo mínimo previsto (45 días)", "Lowest expected balance (45 days)"))
                            MoneyText(lowest, style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
                Row(Modifier.fillMaxWidth().testTag("home.status.facts"), horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s4)) {
                    Fact(tx("Ingresos", "Income"), status.income, MoneyFormat.Sign.INCOME, tx("Sin registrar", "Not recorded"))
                    Fact(tx("Gastos", "Expenses"), status.expenses, MoneyFormat.Sign.EXPENSE, tx("Sin registrar", "Not recorded"))
                    if (status.headline == HomeStatus.Headline.SAFE_TO_SPEND) Fact(tx("Resultado del mes", "Month result"), status.result, MoneyFormat.Sign.NONE, "—")
                }
                status.debtPaid?.let { Box(Modifier.testTag("home.status.debtPaid")) { AmountLine(tx("Pagado a deudas", "Paid to debts"), it) } }
                status.debtBalance?.let { Box(Modifier.testTag("home.status.debtBalance")) { AmountLine(tx("Deuda pendiente", "Outstanding debt"), it) } }
                status.budget?.let { budget ->
                    Column(Modifier.testTag("home.status.budget"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
                        AmountLine(tx("Presupuesto restante", "Budget left"), budget.remaining)
                        DincrProgressBar(budget.used, overMeaning = TrendMeaning.UNFAVORABLE)
                    }
                }
                status.pending?.let { pending ->
                    Row(Modifier.fillMaxWidth().testTag("home.status.pending").semantics(mergeDescendants = true) {}) {
                        Text(tx("Próximos pagos conocidos este mes", "Known upcoming payments this month"), style = MaterialTheme.typography.bodyMedium,
                            color = Dincr.colors.text2, modifier = Modifier.weight(1f))
                        Text(pendingText(pending), style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text)
                    }
                }
            }
        }
    }
}

@Composable
private fun Fact(label: String, amount: BigDecimal?, sign: MoneyFormat.Sign, unknown: String) {
    Column(Modifier.semantics(mergeDescendants = true) {}) {
        Text(label, style = MaterialTheme.typography.bodySmall, color = Dincr.colors.textMuted)
        if (amount != null) MoneyText(amount, sign = sign, style = MaterialTheme.typography.labelLarge)
        else Text(unknown, style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2)
    }
}

/** Payments the calendar knows of (scheduled from today on): none known is not "none due". */
@Composable
private fun pendingText(pending: HomeStatus.Pending): String {
    if (pending.count == 0) return tx("Ninguno registrado", "None recorded")
    val count = if (pending.count == 1) tx("1 pago", "1 payment") else tx("${pending.count} pagos", "${pending.count} payments")
    val total = pending.total ?: return tx("$count · monto por confirmar", "$count · amount to confirm")
    return "$count · ${Dincr.money.format(total)}"
}

/** Why a figure is unknown and where to give DINCR what it needs (never an estimate). */
@Composable
private fun MissingInputs(missing: List<HomeInput>, tagPrefix: String, open: (HomeDestination) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
        if (missing.isEmpty()) Caption(tx("Aún no tengo suficiente información para calcular esto.", "I don’t have enough information to calculate this yet."))
        missing.forEach { input ->
            Text(input.explanation, style = MaterialTheme.typography.bodySmall, color = Dincr.colors.text2)
            TextButton({ open(input.destination) }, Modifier.testTag("$tagPrefix.missing.${input.code}")) { Text(input.actionTitle, color = Dincr.colors.tint) }
        }
    }
}

private val HomeInput.explanation: String
    get() = when (this) {
        HomeInput.INCOME -> tx("DINCR necesita tus ingresos del mes registrados (tu salario o boleta de pago) para calcularlo.",
            "DINCR needs this month’s income recorded (your salary or pay stub) to calculate it.")
        HomeInput.ESSENTIAL_EXPENSES -> tx("Faltan tus gastos esenciales del mes.", "Your essential monthly expenses are missing.")
        HomeInput.DEBT_PAYMENTS -> tx("Una de tus deudas no tiene su cuota mensual.", "One of your debts has no monthly payment.")
        HomeInput.SAVINGS -> tx("Falta tu ahorro disponible o el saldo de una cuenta.", "Your available savings or an account balance is missing.")
        HomeInput.EMERGENCY_FUND_TARGET -> tx("Falta la meta de tu fondo de emergencia.", "Your emergency fund target is missing.")
        HomeInput.DEBT_INTEREST_RATES -> tx("Falta la tasa de interés de una o más deudas. Con todas las tasas, DINCR puede decirte qué deuda atacar primero.",
            "The interest rate of one or more debts is missing. With every rate, DINCR can tell you which debt to pay down first.")
    }

private val HomeInput.actionTitle: String
    get() = when (this) {
        HomeInput.INCOME -> tx("Registrar ingreso", "Record income")
        HomeInput.DEBT_PAYMENTS, HomeInput.DEBT_INTEREST_RATES -> tx("Revisar deudas", "Review debts")
        HomeInput.ESSENTIAL_EXPENSES, HomeInput.SAVINGS, HomeInput.EMERGENCY_FUND_TARGET -> tx("Completar mi situación", "Complete my situation")
    }

// 3. Qué sigue

@Composable
private fun HomeNextCard(next: HomeNext, open: (HomeDestination) -> Unit) {
    Column(Modifier.testTag("home.next"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
        SectionTitle(tx("Qué sigue", "What’s next"))
        DincrCard {
            Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                Row(Modifier.semantics(mergeDescendants = true) {}, verticalAlignment = Alignment.Top) {
                    RoundedIcon(next.icon)
                    Column(Modifier.weight(1f).padding(start = DincrSpacing.s3), verticalArrangement = Arrangement.spacedBy(2.dp)) {
                        Text(next.titleText, style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
                        next.detailText?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2) }
                        if (next.kind == HomeNext.Kind.COMMITMENT) {
                            if (next.amount != null) MoneyText(next.amount, style = MaterialTheme.typography.labelLarge)
                            else Text(tx("Monto por confirmar", "Amount to confirm"), style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2)
                        }
                    }
                }
                if (next.kind == HomeNext.Kind.NEEDS_INFORMATION && next.missing.isNotEmpty()) {
                    MissingInputs(next.missing, "home.next", open)
                } else {
                    TextButton({ open(next.destination) }, Modifier.testTag("home.next.action")) { Text("${next.actionTitle} ›", color = Dincr.colors.tint) }
                }
                if (next.kind == HomeNext.Kind.RECOMMENDATION) FinancialDisclaimer()
            }
        }
    }
}

private val HomeNext.icon: ImageVector
    get() = when (kind) {
        HomeNext.Kind.RECOMMENDATION -> Icons.Rounded.AutoAwesome
        HomeNext.Kind.NEEDS_INFORMATION -> Icons.Rounded.HelpOutline
        HomeNext.Kind.COMMITMENT -> Icons.Rounded.CalendarMonth
        HomeNext.Kind.REGISTER_INCOME -> Icons.Rounded.SouthWest
        HomeNext.Kind.REGISTER_MOVEMENT -> Icons.Rounded.AddCircleOutline
    }

private val HomeNext.titleText: String
    get() = when (kind) {
        HomeNext.Kind.RECOMMENDATION -> title.orEmpty()
        HomeNext.Kind.NEEDS_INFORMATION -> title ?: tx("DINCR necesita más información antes de recomendarte.", "DINCR needs more information before recommending.")
        HomeNext.Kind.COMMITMENT -> tx("Próximo pago: ${title ?: "deuda"}", "Next payment: ${title ?: "debt"}")
        HomeNext.Kind.REGISTER_INCOME -> tx("Registrá tus ingresos del mes", "Record this month’s income")
        HomeNext.Kind.REGISTER_MOVEMENT -> tx("Mantené tu mes al día", "Keep your month up to date")
    }

private val HomeNext.detailText: String?
    get() = when (kind) {
        HomeNext.Kind.RECOMMENDATION -> detail
        HomeNext.Kind.NEEDS_INFORMATION -> null
        HomeNext.Kind.COMMITMENT -> date?.let(::dateLabel)
        HomeNext.Kind.REGISTER_INCOME -> tx("Con tu salario o boleta de pago registrados, DINCR puede mostrarte el resultado del mes.",
            "With your salary or pay stub recorded, DINCR can show you this month’s result.")
        HomeNext.Kind.REGISTER_MOVEMENT -> tx("Registrá tus gastos e ingresos para ver tu mes completo.", "Record your expenses and income to see your whole month.")
    }

private val HomeNext.actionTitle: String
    get() = when (kind) {
        HomeNext.Kind.RECOMMENDATION -> tx("Ver tu plan del mes", "See your plan for the month")
        HomeNext.Kind.NEEDS_INFORMATION -> tx("Completar mi situación", "Complete my situation")
        HomeNext.Kind.COMMITMENT -> tx("Ver deudas", "See debts")
        HomeNext.Kind.REGISTER_INCOME -> tx("Registrar ingreso", "Record income")
        HomeNext.Kind.REGISTER_MOVEMENT -> tx("Registrar movimiento", "Record a transaction")
    }

// 4. Accesos rápidos

@Composable
private fun HomeShortcuts(shortcuts: List<HomeShortcut>, open: (HomeDestination) -> Unit) {
    Column(Modifier.testTag("home.shortcuts"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
        SectionTitle(tx("Accesos rápidos", "Quick access"))
        shortcuts.chunked(2).forEach { row ->
            Row(horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
                row.forEach { shortcut ->
                    Box(Modifier.weight(1f).testTag(shortcut.tag)) {
                        DincrCard(Modifier.fillMaxWidth().heightIn(min = 88.dp).clickable { open(shortcut.destination) }) {
                            Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                                RoundedIcon(shortcut.icon)
                                Text(shortcut.title, style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text)
                            }
                        }
                    }
                }
                if (row.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

/** Debts and goals keep the texts the reachability spec names ("Deudas", "Metas y ahorros"). */
private val HomeShortcut.title: String
    get() = when (this) {
        HomeShortcut.REGISTER_MOVEMENT -> tx("Registrar movimiento", "Record a transaction")
        HomeShortcut.MOVEMENTS -> tx("Movimientos", "Transactions")
        HomeShortcut.DEBTS -> tx("Deudas", "Debts")
        HomeShortcut.GOALS -> tx("Metas y ahorros", "Goals and savings")
    }

private val HomeShortcut.tag: String
    get() = when (this) {
        HomeShortcut.REGISTER_MOVEMENT -> "home.shortcut.registerMovement"
        HomeShortcut.MOVEMENTS -> "home.shortcut.movements"
        HomeShortcut.DEBTS -> "home.debts"
        HomeShortcut.GOALS -> "home.goals"
    }

private val HomeShortcut.icon: ImageVector
    get() = when (this) {
        HomeShortcut.REGISTER_MOVEMENT -> Icons.Rounded.AddCircleOutline
        HomeShortcut.MOVEMENTS -> Icons.AutoMirrored.Rounded.ReceiptLong
        HomeShortcut.DEBTS -> Icons.Rounded.CreditCard
        HomeShortcut.GOALS -> Icons.Rounded.Flag
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

fun shortMonth(period: String): String {
    val month = period.substringAfter('-').toIntOrNull() ?: return period
    val names = if (tx("es", "en") == "es") listOf("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic")
    else listOf("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    return names.getOrElse(month - 1) { period }
}
