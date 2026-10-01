package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AppLanguage
import com.dincr.data.DirectorStrategy
import com.dincr.data.Distribution
import com.dincr.data.OpsFlag
import com.dincr.data.Strategy
import com.dincr.data.StrategyContract
import com.dincr.data.StrategyDashboard
import com.dincr.design.BannerTone
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.EmptyState
import com.dincr.design.MoneyText
import com.dincr.design.StatusBanner
import com.dincr.design.generated.DincrSpacing

/**
 * Plan → Estrategia and Plan → Distribución de dinero: two views of the SAME strategy response, read
 * from the contract of the identity ([StrategyContract]): Basic → strategy-basic, VIP users →
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
        DincrPrimaryButton(tx("Ver planes", "See plans"), { nav.open("plans") })
    }
}

@Composable
private fun NeedsIncome(message: String?, nav: Navigator) {
    EmptyState(Icons.Rounded.AutoAwesome, tx("Necesitamos tus ingresos", "We need your income"), message ?: tx("Registrá tus ingresos o completá tu situación financiera para armar tu estrategia.", "Record your income or complete your financial situation to build your strategy.")) {
        DincrPrimaryButton(tx("Completar situación", "Complete situation"), { nav.open("situation") })
    }
}

/** The observed-income note: the income was estimated from recorded income, not declared. */
@Composable
private fun ObservedIncomeNote() {
    StatusBanner(BannerTone.INFO, tx("Ingreso estimado", "Estimated income"), tx("Estimado con tus ingresos registrados (no declarado)", "Estimated from your recorded income (not declared)"))
}

/** F2/F3 — Plan → Estrategia. */
@Composable
fun StrategyScreen(model: AppModel, nav: Navigator) {
    val (contract, strategy) = rememberStrategy(model)
    LaunchedEffect(Unit) { model.recordScreen("strategy_opened", "strategy") }
    DetailScaffold(tx("Estrategia", "Strategy"), nav::back) {
        if (contract == null) { LockedStrategy(nav); return@DetailScaffold }
        LoadContent(strategy) { data ->
            when (data) {
                is StrategyData.Basic -> BasicStrategyView(data.strategy, nav)
                is StrategyData.Director -> data.dashboard.strategy?.let { DirectorStrategyView(it, nav) }
                    ?: EmptyState(Icons.Rounded.AutoAwesome, tx("Sin estrategia todavía", "No strategy yet"), data.dashboard.content.orEmpty())
            }
        }
        FinancialDisclaimer()
    }
}

@Composable
private fun BasicStrategyView(s: Strategy, nav: Navigator) {
    if (s.status == "needs_income") { NeedsIncome(s.recommendation, nav); return }
    if (s.isIncomeObserved) ObservedIncomeNote()
    if (s.status == "critical") StatusBanner(BannerTone.WARNING, tx("Tus compromisos superan tus ingresos", "Your commitments exceed your income"), s.recommendation.orEmpty())
    DincrCard {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
            Text(tx("Margen para decidir", "Room to decide"), style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2)
            MoneyText(s.strategicMargin, style = MaterialTheme.typography.displaySmall)
            AmountLine(tx("Ingresos del mes", "Monthly income"), s.monthlyIncome)
            AmountLine(tx("Gastos esenciales", "Essential expenses"), s.essentialExpenses)
            AmountLine(tx("Cuotas mínimas", "Minimum payments"), s.minimumDebtPayments)
        }
    }
    if (s.status != "critical") s.recommendation?.let { Section(tx("Recomendación", "Recommendation")) { Text(it, style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text) } }
    s.projection?.let { p ->
        Section(tx("Tu deuda prioritaria", "Your priority debt")) {
            p.name?.let { Text(it, style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text) }
            p.monthlyToTarget?.let { AmountLine(tx("Pago mensual sugerido", "Suggested monthly payment"), it) }
            p.months?.let { m -> InfoLine(tx("Terminás en", "Paid off in"), tx("$m meses", "$m months") + (p.baselineMonths?.let { tx(" (vs $it pagando el mínimo)", " (vs $it paying the minimum)") } ?: "")) }
        }
    }
    LinkButton(tx("Ver cómo repartir tu dinero", "See how to split your money")) { nav.open("distribution") }
    s.warnings.takeIf { it.isNotEmpty() }?.let { warnings -> Section(tx("Tené en cuenta", "Keep in mind")) { warnings.forEach { Text("• $it", style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2) } } }
}

@Composable
private fun LinkButton(label: String, onClick: () -> Unit) =
    androidx.compose.material3.TextButton(onClick) { Text(label, color = Dincr.colors.tint) }

/** Where the monthly income comes from, as the backend's income policy says. */
private fun incomeSourceNote(source: String?): String? = when (source) {
    "observed" -> tx("Estimado con tus ingresos registrados (no declarado)", "Estimated from your recorded income (not declared)")
    "declared" -> tx("Ingreso declarado en tu situación financiera", "Income declared in your financial situation")
    else -> null
}

@Composable
private fun DirectorStrategyView(s: DirectorStrategy, nav: Navigator) {
    if (s.status == "needs_income") { NeedsIncome(s.objective, nav); return }
    if (s.incomePolicy?.source == "observed") ObservedIncomeNote()
    if (s.status == "critical") StatusBanner(BannerTone.WARNING, tx("Este mes no hay sobrante real", "No real surplus this month"), s.objective.orEmpty())
    DincrCard {
        Column(Modifier.testTag("strategy.director.${s.scope}"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
            s.modeLabel?.let { Text(it, style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2) }
            s.priority?.title?.let { Text(it, style = MaterialTheme.typography.titleLarge, color = Dincr.colors.text) }
            s.priority?.detail?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2) }
            if (s.status != "critical") s.objective?.let { Caption(it) }
        }
    }
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
    LinkButton(tx("Ver cómo repartir tu dinero", "See how to split your money")) { nav.open("distribution") }
    if (s.rules.isNotEmpty()) Section(tx("Reglas", "Rules")) { s.rules.forEach { Text("• $it", style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2) } }
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
    AmountCard(tx("Margen para repartir", "Margin to split"), s.strategicMargin)
    if (s.allocations.isEmpty()) Caption(tx("Este mes no hay margen para repartir.", "There’s no margin to split this month."))
    else Section(tx("Cómo repartir tu margen", "How to split your margin")) { s.allocations.forEach { AmountLine(it.label ?: it.bucket.orEmpty(), it.amount) } }
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
    AmountCard(tx("Sobrante a repartir", "Surplus to allocate"), s.allocationBaseAmount)
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
