package com.dincr.app.ui

import com.dincr.data.Feature
import androidx.compose.material.icons.rounded.CalendarMonth
import androidx.compose.material.icons.rounded.PieChart
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.ExpandLess
import androidx.compose.material.icons.rounded.ExpandMore
import androidx.compose.material.icons.rounded.Tune
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlin.math.roundToInt
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AppLanguage
import com.dincr.data.DirectorStrategy
import com.dincr.data.Distribution
import com.dincr.data.MessageKind
import com.dincr.data.MonthPlan
import com.dincr.data.OpsFlag
import com.dincr.data.ProgressValue
import com.dincr.data.Strategy
import com.dincr.data.StrategyContract
import com.dincr.data.StrategyDashboard
import com.dincr.design.BannerTone
import com.dincr.design.CompositionDonut
import com.dincr.design.Dincr
import com.dincr.data.PlanTier
import com.dincr.data.RecommendedPriority
import com.dincr.design.DincrCard
import com.dincr.design.DincrMessage
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.DincrProgressBar
import com.dincr.design.EmptyState
import com.dincr.design.MoneyText
import com.dincr.design.StatusBanner
import com.dincr.design.generated.DincrSpacing

/**
 * Plan → "Tu plan del mes" and Plan → Distribución de dinero: views of the SAME strategy response,
 * read from the contract of the identity ([StrategyContract]): Basic → strategy-basic, VIP users →
 * vip/strategy-dashboard, the Owner (server role) → jarvis/premium/strategy-dashboard. The backend
 * computes every figure; these screens only format them.
 */
sealed interface StrategyData {
    data class Basic(val strategy: Strategy) : StrategyData
    data class Director(val dashboard: StrategyDashboard) : StrategyData
}

@Composable
private fun rememberStrategy(model: AppModel): Pair<StrategyContract?, LoadHandle<StrategyData>> {
    val profile by model.profile.collectAsStateWithLifecycle()
    val flags by model.flags.collectAsStateWithLifecycle()
    val contract = StrategyContract.of(profile, flags.isEnabled(OpsFlag.VIP_INTELLIGENCE))
    return contract to rememberLoad(model, contract) {
        when (contract) {
            StrategyContract.OWNER -> StrategyData.Director(model.api.ownerStrategyDashboard())
            StrategyContract.VIP_USERS -> StrategyData.Director(model.api.strategyDashboard())
            else -> StrategyData.Basic(model.api.strategyBasic())
        }
    }
}

@Composable
private fun LockedStrategy(nav: Navigator) {
    EmptyState(Icons.Rounded.AutoAwesome, tx("Disponible desde Basic", "Available from Basic"), tx("La estrategia y la distribución de tu dinero llegan con Basic.", "Strategy and money distribution come with Basic.")) {
        DincrPrimaryButton(tx("Ver suscripciones", "See subscriptions"), { nav.open("plans") })
    }
}

@Composable
private fun NeedsIncome(message: String?, nav: Navigator) {
    EmptyState(Icons.Rounded.AutoAwesome, tx("Necesitamos tus ingresos", "We need your income"), message ?: tx("Registrá tus ingresos o completá Ingresos y base para armar tu estrategia.", "Record your income or complete Income and base to build your strategy.")) {
        DincrPrimaryButton(tx("Completar ingresos y base", "Complete income and base"), { nav.open("incomeBase") })
    }
}

/** The observed-income note: the income was estimated from recorded income, not declared. */
@Composable
private fun ObservedIncomeNote() {
    StatusBanner(BannerTone.INFO, tx("Ingreso estimado", "Estimated income"), tx("Estimado con tus ingresos registrados (no declarado)", "Estimated from your recorded income (not declared)"))
}

/**
 * UX-3 — Plan → "Tu plan del mes": Estrategia and Distribución as one plan, from the same strategy
 * response. First the amount to plan, how DINCR splits it and why in one sentence; the derivation
 * and every historical detail stay one tap away ("¿Por qué?", "Ver todo el detalle"). Nothing here
 * computes a figure: [MonthPlan] only reads the response. Distribución de dinero keeps its own
 * screen as a transitional access.
 */
/**
 * §15 PR 5 (option A) — "Para organizar tu mes": Presupuesto and Calendario financiero, the existing
 * screens, inside Tu plan del mes (Plan keeps its six entries). From Basic; §15 PR 10 (option A): Free opens
 * Tu plan del mes in its locked state and sees both here, locked, opening Suscripción. iOS: `OrganizeYourMonth`.
 */
@Composable
private fun OrganizeYourMonth(plan: PlanTier, nav: Navigator) {
    SectionTitle(tx("Para organizar tu mes", "To organize your month"))
    DincrCard {
        Column {
            if (plan.allows(Feature.GUIDED_BUDGET)) {
                Box(Modifier.testTag("plan.month.budget")) { NavRow(Icons.Rounded.PieChart, tx("Presupuesto", "Budget"), tx("Límites por categoría", "Limits by category")) { nav.open("budget") } }
                Box(Modifier.testTag("plan.month.calendar")) { NavRow(Icons.Rounded.CalendarMonth, tx("Calendario financiero", "Financial calendar"), tx("Pagos e ingresos del mes", "Payments and income this month")) { nav.open("calendar") } }
            } else {
                val locked = tx("Disponible desde Basic", "Available from Basic")
                Box(Modifier.testTag("plan.month.budget")) { NavRow(Icons.Rounded.PieChart, tx("Presupuesto", "Budget"), locked, badge = "Basic") { nav.open("plans") } }
                Box(Modifier.testTag("plan.month.calendar")) { NavRow(Icons.Rounded.CalendarMonth, tx("Calendario financiero", "Financial calendar"), locked, badge = "Basic") { nav.open("plans") } }
            }
        }
    }
}

@Composable
fun StrategyScreen(model: AppModel, nav: Navigator) {
    val (contract, strategy) = rememberStrategy(model)
    LaunchedEffect(Unit) { model.recordScreen("strategy_opened", "strategy") }
    DetailScaffold(tx("Tu plan del mes", "Your plan for the month"), nav::back) {
        val profile by model.profile.collectAsStateWithLifecycle()
        // §15 PR 10 (option A): the locked state keeps the group below, with Presupuesto and Calendario locked.
        if (contract == null) LockedStrategy(nav) else LoadContent(strategy) { data ->
            when (data) {
                is StrategyData.Basic -> BasicMonthPlan(data.strategy, nav)
                is StrategyData.Director -> data.dashboard.strategy?.let { DirectorMonthPlan(it, MonthPlan.of(data.dashboard), nav) }
                    ?: EmptyState(Icons.Rounded.AutoAwesome, tx("Sin plan todavía", "No plan yet"), data.dashboard.content.orEmpty())
            }
        }
        if (profile?.planTier == PlanTier.VIP) Box(Modifier.testTag("plan.month.preferences")) {
            // UX-7: the personal minimum (UX-8: the priority is DINCR's recommendation, not a setting).
            DincrCard { NavRow(Icons.Rounded.Tune, tx("Ajustes del plan", "Plan settings"), tx("Mínimo personal por mes", "Personal minimum per month")) { nav.open("planPreferences") } }
        }
        OrganizeYourMonth(profile?.planTier ?: PlanTier.FREE, nav)
        FinancialDisclaimer()
    }
}

@Composable
private fun BasicMonthPlan(s: Strategy, nav: Navigator) {
    val plan = MonthPlan.of(s)
    if (plan.needsIncome) { NeedsIncome(s.recommendation, nav); return }
    if (plan.usesObservedIncome) ObservedIncomeNote()
    if (plan.isCritical) DincrMessage(MessageKind.ATTENTION, tx("Tus compromisos superan tus ingresos", "Your commitments exceed your income"), plan.criticalDetail.orEmpty())
    // UX-8: DINCR's recommended priority and why (the Basic engine's own; Free has no strategy).
    val recommended = RecommendedPriority.of(s)
    MonthPlanSummary(plan, tx("Libre después de tus compromisos", "Left after your commitments"), "strategy.basic", showsHeadline = recommended == null)
    recommended?.let { RecommendedPriorityCard(it) }
    MonthPlanSplit(plan)
    // Cautions stay in sight, never behind "¿Por qué?".
    s.warnings.takeIf { it.isNotEmpty() }?.let { warnings -> Section(tx("Tené en cuenta", "Keep in mind")) { warnings.forEach { Text("• $it", style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2) } } }
    Disclosure(tx("¿Por qué DINCR recomienda esto?", "Why does DINCR recommend this?"), "plan.month.why") {
        Section(tx("Tu mes", "Your month")) {
            AmountLine(tx("Ingresos del mes", "Monthly income"), s.monthlyIncome)
            AmountLine(tx("Gastos esenciales", "Essential expenses"), s.essentialExpenses)
            AmountLine(tx("Cuotas mínimas", "Minimum payments"), s.minimumDebtPayments)
            AmountLine(tx("Libre después de tus compromisos", "Left after your commitments"), s.strategicMargin, emphasize = true)
        }
        s.projection?.let { p ->
            Section(tx("Tu deuda prioritaria", "Your priority debt")) {
                p.name?.let { Text(it, style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text) }
                p.monthlyToTarget?.let { AmountLine(tx("Pago mensual sugerido", "Suggested monthly payment"), it) }
                p.months?.let { m -> InfoLine(tx("Terminás en", "Paid off in"), tx("$m meses", "$m months") + (p.baselineMonths?.let { tx(" (vs $it pagando el mínimo)", " (vs $it paying the minimum)") } ?: "")) }
            }
        }
        s.nextPaycheck?.takeIf { it.envelopes.isNotEmpty() }?.let { p ->
            Section(tx("Tu próximo ingreso", "Your next paycheck")) {
                AmountLine(tx("Estimado", "Estimated"), p.estimatedPaycheck, emphasize = true)
                p.envelopes.forEach { AmountLine(it.label ?: it.bucket.orEmpty(), it.amount) }
                p.unassigned?.takeIf { it.signum() != 0 }?.let { AmountLine(tx("Sin asignar", "Unassigned"), it) }
            }
        }
    }
}

@Composable
private fun DirectorMonthPlan(s: DirectorStrategy, plan: MonthPlan, nav: Navigator) {
    if (plan.needsIncome) { NeedsIncome(s.objective, nav); return }
    if (s.incomePolicy?.source in ESTIMATED_INCOME) ObservedIncomeNote()
    if (plan.isCritical) DincrMessage(MessageKind.ATTENTION, tx("Este mes no hay sobrante real", "No real surplus this month"), plan.criticalDetail.orEmpty())
    // UX-8: DINCR's recommended priority and why (the dashboard's own).
    val recommended = RecommendedPriority.of(s)
    MonthPlanSummary(plan, tx("Sobrante para repartir", "Surplus to allocate"), "strategy.director.${s.scope}", showsHeadline = recommended == null)
    recommended?.let { RecommendedPriorityCard(it) }
    MonthPlanSplit(plan)
    // VIP (Users): Basic's cautions, and the way to complete a missing debt rate.
    s.warnings.takeIf { it.isNotEmpty() }?.let { warnings -> Section(tx("Tené en cuenta", "Keep in mind")) { warnings.forEach { Text("• $it", style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2) } } }
    if (s.needsDebtRates) Box(Modifier.testTag("plan.month.debtRates")) { LinkButton(tx("Revisar deudas", "Review debts")) { nav.open("debts") } }
    Disclosure(tx("¿Por qué DINCR recomienda esto?", "Why does DINCR recommend this?"), "plan.month.why") {
        DincrCard {
            Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
                s.modeLabel?.let { Text(it, style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2) }
                s.priority?.detail?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2) }
                if (s.status != "critical" && s.priority?.title != null) s.objective?.let { Caption(it) }
            }
        }
        val language = AppLanguage.current()
        val lines = Distribution.formulaLines(s)
        if (lines.isNotEmpty()) Section(tx("De dónde sale", "Where it comes from")) {
            lines.forEach { (key, amount) -> AmountLine(Distribution.formulaLabel(key, language), amount, emphasize = key == "surplus") }
        }
    }
    Disclosure(tx("Ver todo el detalle", "See full details"), "plan.month.detail") {
        Section(if (s.isOwnerScope) tx("Este ciclo", "This cycle") else tx("Este mes", "This month")) {
            AmountLine(tx("Ingresos del mes", "Monthly income"), s.monthlyIncome, emphasize = true)
            incomeSourceNote(s.incomePolicy?.source)?.let { Caption(it) }
            AmountLine(if (s.isOwnerScope) tx("Gastos comprometidos", "Committed spending") else tx("Gastos registrados este mes", "Spending recorded this month"), s.monthlyExpenses)
            AmountLine(tx("Compromiso de deudas", "Debt commitment"), s.debtCommitmentCurrentCycle)
            s.pendingRecurringTotal?.let { AmountLine(tx("Pagos recurrentes pendientes", "Pending recurring payments"), it) }
            AmountLine(tx("Podés gastar con tranquilidad", "Safe to spend"), s.safeToSpend, emphasize = true)
        }
        if (s.isOwnerScope) OwnerCycle(s)
        s.emergencyFund?.let { e ->
            Section(tx("Salvavidas", "Emergency fund")) {
                // Unknown savings stay unknown: "Sin dato", never zero.
                if (s.emergencyKnown) AmountLine(tx("Ahorrado", "Saved"), e.current) else InfoLine(tx("Ahorrado", "Saved"), tx("Sin dato", "No data"))
                AmountLine(tx("Base mensual", "Monthly base"), e.monthlyBase)
                AmountLine(tx("Próxima meta", "Next target"), e.nextTarget)
                if (s.emergencyKnown) {
                    AmountLine(tx("Te falta", "Still to go"), e.gapToNextTarget)
                    emergencyLevel(e.level)?.let { InfoLine(tx("Etapa", "Stage"), it) }
                }
                LinkButton(tx("Ver Salvavidas", "See emergency fund")) { nav.open("salvavidas") }
            }
        }
        if (s.timeline.isNotEmpty() || (s.totalDebt?.signum() ?: 0) > 0) Section(tx("Tus deudas", "Your debts")) {
            AmountLine(tx("Deuda total", "Total debt"), s.totalDebt)
            s.debtProgressPercent?.let { ProgressLine(it / 100.0, tx("${it.toInt()} % pagado", "${it.toInt()} % paid")) }
            s.estimatedDebtFreeDate?.let { InfoLine(tx("Libre de deudas", "Debt-free"), dateLabel(it)) }
            s.timeline.sortedBy { it.priority ?: Int.MAX_VALUE }.forEach { item ->
                Column {
                    AmountLine("${item.priority ?: ""}. ${item.name.orEmpty()}", item.recommendedPayment)
                    Caption(listOfNotNull(item.remainingAmount?.let { tx("Saldo ", "Balance ") + Dincr.money.format(it) }, item.estimatedPayoffDate?.let { tx("termina ", "ends ") + dateLabel(it) }).joinToString(" · "))
                }
            }
        }
        s.investmentRecommended?.takeIf { it.signum() > 0 }?.let { AmountLine(tx("Inversión recomendada", "Recommended investment"), it) }
        if (s.rules.isNotEmpty()) Section(tx("Reglas", "Rules")) { s.rules.forEach { Text("• $it", style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2) } }
    }
}

/** The result first: the amount DINCR plans with and, in one sentence, what it recommends. */
@Composable
private fun MonthPlanSummary(plan: MonthPlan, label: String, tag: String, showsHeadline: Boolean = true) {
    DincrCard {
        Column(Modifier.testTag(tag), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
            Text(label, style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2)
            MoneyText(plan.base, style = MaterialTheme.typography.displaySmall)
            // The headline says the same as the recommended priority, so it is left out when that is shown.
            if (showsHeadline) plan.summaryHeadline?.let { Text(it, style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text) }
        }
    }
}

/**
 * UX-8 — "Recomendación de DINCR": the priority the engine already recommends and why. It is not a
 * setting: the engines name one priority and no other option, so there is nothing to change here.
 */
@Composable
private fun RecommendedPriorityCard(priority: RecommendedPriority) {
    DincrCard {
        Column(Modifier.testTag("plan.month.recommendedPriority").semantics(mergeDescendants = true) {}, verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
            Text(tx("Recomendación de DINCR", "DINCR’s recommendation"), style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2)
            Text(priority.title, style = MaterialTheme.typography.titleLarge, color = Dincr.colors.text)
            priority.why?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2) }
        }
    }
}

/**
 * How DINCR splits the amount. A donut only when the parts exactly make up the amount
 * ([MonthPlan.showsComposition]); otherwise each part as the backend sent it.
 */
@Composable
private fun MonthPlanSplit(plan: MonthPlan) {
    val title = tx("Cómo DINCR lo reparte", "How DINCR splits it")
    Section(title) {
        Column(Modifier.testTag("plan.month.split"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
            when {
                plan.parts.isEmpty() -> Caption(
                    if (plan.kind == MonthPlan.Kind.BASIC) tx("Este mes no queda dinero libre para repartir.", "There’s no money left to split this month.")
                    else tx("Este mes no hay sobrante real para repartir.", "There’s no real surplus to allocate this month."),
                )
                plan.showsComposition -> CompositionDonut(title, plan.composition)
                else -> plan.parts.forEach { part ->
                    Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
                        AmountLine(part.label + (part.percentage?.let { " · ${it.roundToInt()} %" } ?: ""), part.amount)
                        // The backend's own share, when it sent one; never a bar for an unknown share.
                        part.percentage?.let { DincrProgressBar(ProgressValue.ofFraction(it / 100)) }
                    }
                }
            }
        }
    }
}

/** A section that opens on tap: the plan shows the result first and keeps the detail one tap away. */
@Composable
private fun Disclosure(title: String, tag: String, content: @Composable () -> Unit) {
    var open by rememberSaveable { mutableStateOf(false) }
    Column(Modifier.testTag(tag)) {
        Row(
            Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable(role = Role.Button, onClickLabel = title) { open = !open }
                .semantics { stateDescription = if (open) tx("Abierto", "Expanded") else tx("Cerrado", "Collapsed") },
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(title, style = MaterialTheme.typography.titleSmall, color = Dincr.colors.tint, modifier = Modifier.weight(1f))
            Icon(if (open) Icons.Rounded.ExpandLess else Icons.Rounded.ExpandMore, contentDescription = null, tint = Dincr.colors.tint)
        }
        if (open) Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) { content() }
    }
}

@Composable
private fun LinkButton(label: String, onClick: () -> Unit) =
    androidx.compose.material3.TextButton(onClick) { Text(label, color = Dincr.colors.tint) }

/** Income sources that are an estimate from recorded income, not a declared value. */
private val ESTIMATED_INCOME = setOf("observed", "recorded")

/**
 * Where the monthly income comes from: Basic's `income_source` (`observed`) or the VIP income
 * policy's `source` (`recorded`, `declared_capped_by_recorded`, `declared`).
 */
private fun incomeSourceNote(source: String?): String? = when (source) {
    in ESTIMATED_INCOME -> tx("Estimado con tus ingresos registrados (no declarado)", "Estimated from your recorded income (not declared)")
    "declared_capped_by_recorded" -> tx("Ingreso declarado, ajustado a lo que registraste", "Declared income, capped by what you recorded")
    "declared" -> tx("Ingreso declarado", "Declared income")
    else -> null
}

private fun emergencyLevel(level: String?): String? = when (level) {
    "mini_fund_building" -> tx("Construyendo el mini fondo", "Building the mini fund")
    "one_month_building" -> tx("Camino a 1 mes", "On the way to 1 month")
    "three_month_building" -> tx("Camino a 3 meses", "On the way to 3 months")
    "strong" -> tx("Sólido", "Strong")
    else -> null
}

/** The Owner's cycle (historical JARVIS model). Portfolio amounts stay in their own currency. */
@Composable
private fun OwnerCycle(s: DirectorStrategy) {
    Section(tx("Tu ciclo", "Your cycle")) {
        AmountLine(tx("Ingreso recurrente", "Recurring income"), s.recurringMonthlyIncome)
        AmountLine(tx("Extras del mes (OT, bonos, feriados)", "This month’s extras (OT, bonuses, holidays)"), s.currentMonthExtraNet)
        AmountLine(tx("Recibido en el ciclo", "Received this cycle"), s.incomeReceivedCurrentCycle)
        AmountLine(tx("Por recibir en el ciclo", "Still to receive this cycle"), s.remainingIncomeCurrentCycle)
        AmountLine(tx("Efectivo distribuible", "Distributable cash"), s.distributableAccountCash)
        AmountLine(tx("Gastos del estado de cuenta", "Statement spending"), s.statementExpenses)
        AmountLine(tx("Gastos nuevos después del corte", "New spending after the cut"), s.newExpensesAfterCut)
        AmountLine(tx("Fijos obligatorios pendientes", "Pending mandatory fixed expenses"), s.mandatoryFixedPending)
        s.mandatoryFixedPendingItems.forEach { Caption("• ${it.name.orEmpty()} · ${it.amount?.let(Dincr.money::format) ?: "—"}" + (it.dueDate?.let { d -> " · " + dateLabel(d) } ?: "")) }
        s.monthsSavedByCurrentExtras?.takeIf { it > 0 }?.let { InfoLine(tx("Meses ahorrados por los extras", "Months saved by the extras"), it.toString()) }
    }
    s.investmentPortfolio?.let { p ->
        Section(tx("Portafolio de inversión", "Investment portfolio")) {
            AmountLine(tx("Valor de mercado", "Market value"), p.marketValue, currency = p.currency)
            AmountLine(tx("Capital aportado", "Contributed capital"), p.contributedCapital, currency = p.currency)
            AmountLine(tx("Resultado neto", "Net result"), p.netPnl, currency = p.currency)
        }
    }
}

/** Plan → Distribución de dinero: the allocations of the same strategy response. */
@Composable
fun DistributionScreen(model: AppModel, nav: Navigator) {
    val (contract, strategy) = rememberStrategy(model)
    DetailScaffold(tx("Distribución de dinero", "Money distribution"), nav::back) {
        if (contract == null) { LockedStrategy(nav); return@DetailScaffold }
        LoadContent(strategy) { data ->
            when (data) {
                is StrategyData.Basic -> BasicDistribution(data.strategy, nav)
                is StrategyData.Director -> data.dashboard.strategy?.let { DirectorDistribution(it, nav) }
            }
        }
        FinancialDisclaimer()
    }
}

@Composable
private fun BasicDistribution(s: Strategy, nav: Navigator) {
    if (s.status == "needs_income") { NeedsIncome(s.recommendation, nav); return }
    if (s.isIncomeObserved) ObservedIncomeNote()
    AmountCard(tx("Libre después de tus compromisos", "Left after your commitments"), s.strategicMargin)
    if (s.allocations.isEmpty()) Caption(tx("Este mes no queda dinero libre para repartir.", "There’s no money left to split this month."))
    else Section(tx("Cómo repartir lo que te queda", "How to split what’s left")) { s.allocations.forEach { AmountLine(it.label ?: it.bucket.orEmpty(), it.amount) } }
    s.nextPaycheck?.takeIf { it.envelopes.isNotEmpty() }?.let { p ->
        Section(tx("Tu próximo ingreso", "Your next paycheck")) {
            AmountLine(tx("Estimado", "Estimated"), p.estimatedPaycheck, emphasize = true)
            p.envelopes.forEach { AmountLine(it.label ?: it.bucket.orEmpty(), it.amount) }
            p.unassigned?.takeIf { it.signum() != 0 }?.let { AmountLine(tx("Sin asignar", "Unassigned"), it) }
        }
    }
}

@Composable
private fun DirectorDistribution(s: DirectorStrategy, nav: Navigator) {
    if (s.status == "needs_income") { NeedsIncome(s.objective, nav); return }
    val language = AppLanguage.current()
    AmountCard(tx("Sobrante para repartir", "Surplus to allocate"), s.allocationBaseAmount)
    if (s.allocationItems.isEmpty()) Caption(tx("Este mes no hay sobrante real para repartir.", "There’s no real surplus to allocate this month."))
    else Section(tx("Cómo repartir tu sobrante", "How to split your surplus")) {
        s.allocationItems.forEach { item ->
            AmountLine(Distribution.allocationLabel(item, language) + (item.percentage?.let { " · ${it.toInt()} %" } ?: ""), item.amount)
        }
    }
    val lines = Distribution.formulaLines(s)
    if (lines.isNotEmpty()) Section(tx("De dónde sale", "Where it comes from")) {
        lines.forEach { (key, amount) -> AmountLine(Distribution.formulaLabel(key, language), amount, emphasize = key == "surplus") }
    }
}

@Composable
private fun AmountCard(label: String, amount: java.math.BigDecimal?) {
    DincrCard {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
            Text(label, style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2)
            MoneyText(amount, style = MaterialTheme.typography.displaySmall)
        }
    }
}
