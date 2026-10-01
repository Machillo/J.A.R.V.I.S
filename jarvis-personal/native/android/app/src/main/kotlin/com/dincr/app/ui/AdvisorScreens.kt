package com.dincr.app.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.Insights
import androidx.compose.material.icons.rounded.NotificationsActive
import androidx.compose.material.icons.rounded.QueryStats
import androidx.compose.material.icons.rounded.Science
import androidx.compose.material.icons.rounded.Summarize
import androidx.compose.material.icons.rounded.Timeline
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.ApiError
import com.dincr.data.AuthException
import com.dincr.data.Feature
import com.dincr.data.MoneyFormat
import com.dincr.data.OpsFlag
import com.dincr.data.PlanTier
import com.dincr.data.ScenarioRequest
import com.dincr.data.ScenarioResult
import com.dincr.design.BannerTone
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.EmptyState
import com.dincr.design.StatusBanner
import java.math.BigDecimal
import java.time.YearMonth
import kotlinx.coroutines.launch

/** B16 — every advisory screen says what DINCR is and is not. */
@Composable
fun FinancialDisclaimer() {
    Caption(tx("DINCR orienta con tus datos; no es asesoría financiera, legal ni tributaria. Revisá las decisiones importantes con un profesional.",
        "DINCR guides you with your data; it is not financial, legal or tax advice. Check important decisions with a professional."))
}

/** F1 — the DINCR tab: Free → monthly summary; Basic → strategy; VIP → the director's tools. */
@Composable
fun AdvisorHubScreen(model: AppModel, nav: Navigator) {
    val profile by model.profile.collectAsStateWithLifecycle()
    val plan = profile?.planTier ?: PlanTier.FREE
    val vipOn = model.isOn(OpsFlag.VIP_INTELLIGENCE)
    ScreenColumn {
        Text("DINCR", style = MaterialTheme.typography.headlineMedium, color = Dincr.colors.text)
        DincrCard {
            Column {
                NavRow(Icons.Rounded.Summarize, tx("Resumen del mes", "Monthly summary"), tx("Ingresos, gastos y metas por mes", "Income, expenses and goals by month")) { nav.open("monthly") }
                // Estrategia lives in the Plan tab (with Salvavidas and the money distribution).
                if (plan.allows(Feature.BASIC_REPORTS)) {
                    if (model.isOn(OpsFlag.ADVANCED_REPORTS)) NavRow(Icons.Rounded.QueryStats, tx("Reportes", "Reports"), tx("Tu mes comparado con el anterior", "Your month vs the previous one")) { nav.open("reports") }
                } else {
                    NavRow(Icons.Rounded.QueryStats, tx("Reportes", "Reports"), tx("Disponible desde Basic", "Available from Basic"), badge = "Basic") { nav.open("plans") }
                }
            }
        }
        if (plan == PlanTier.VIP && !vipOn) FeaturePaused(model, OpsFlag.VIP_INTELLIGENCE)
        DincrCard {
            Column {
                if (plan == PlanTier.VIP && vipOn) {
                    NavRow(Icons.Rounded.NotificationsActive, tx("DINCR hoy", "DINCR today"), tx("Avisos sobre cambios en tus finanzas", "Alerts about changes in your finances")) { nav.open("today") }
                    NavRow(Icons.Rounded.Timeline, tx("Proyecciones", "Projections"), tx("Cómo se ven tus finanzas en 1 a 12 meses", "Your finances in 1 to 12 months")) { nav.open("projections") }
                    NavRow(Icons.Rounded.Science, tx("Escenarios", "Scenarios"), tx("¿Qué pasa si gano o gasto más?", "What if I earn or spend more?")) { nav.open("scenarios") }
                    NavRow(Icons.Rounded.Insights, tx("Revisión mensual", "Monthly review"), tx("Qué cambió y qué sigue", "What changed and what’s next")) { nav.open("review") }
                } else if (plan != PlanTier.VIP) {
                    NavRow(Icons.Rounded.Timeline, tx("Director financiero", "Financial director"), tx("Proyecciones, escenarios y revisión mensual", "Projections, scenarios and monthly review"), badge = "VIP") { nav.open("plans") }
                }
            }
        }
    }
}

/** F6 — VIP scenarios: what if (never saved). */
@Composable
fun ScenariosScreen(model: AppModel, nav: Navigator) {
    val format = Dincr.money
    var income by remember { mutableStateOf("") }
    var expense by remember { mutableStateOf("") }
    var extra by remember { mutableStateOf("") }
    var incomeDown by remember { mutableStateOf(false) }
    var expenseDown by remember { mutableStateOf(false) }
    var result by remember { mutableStateOf<ScenarioResult?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    DetailScaffold(tx("Escenarios", "Scenarios"), nav::back) {
        Caption(tx("Probá cambios sin guardar nada: DINCR calcula cómo cambiaría tu margen.", "Try changes without saving anything: DINCR shows how your margin would change."))
        fun value(text: String) = if (text.isBlank()) BigDecimal.ZERO else com.dincr.data.AmountInput.parseZeroOrMore(text, format.separators)
        ChoiceChips(listOf(false to tx("Ingreso sube", "Income rises"), true to tx("Ingreso baja", "Income falls")), incomeDown, { incomeDown = it })
        MoneyField(tx("Cambio mensual de ingresos", "Monthly income change"), income, { income = it })
        ChoiceChips(listOf(false to tx("Gasto sube", "Spending rises"), true to tx("Gasto baja", "Spending falls")), expenseDown, { expenseDown = it })
        MoneyField(tx("Cambio mensual de gastos", "Monthly expense change"), expense, { expense = it })
        MoneyField(tx("Dinero extra único", "One-off extra money"), extra, { extra = it })
        error?.let { com.dincr.design.ErrorState(it) }
        DincrPrimaryButton(tx("Calcular", "Calculate"), loading = busy, onClick = {
            val i = value(income); val e = value(expense); val x = value(extra)
            if (i == null || e == null || x == null) { error = tx("Revisá los montos.", "Check the amounts."); return@DincrPrimaryButton }
            busy = true; error = null
            scope.launch {
                model.load(tx("No pudimos calcular el escenario.", "We couldn’t calculate the scenario.")) {
                    model.api.simulate(ScenarioRequest(if (incomeDown) i.negate() else i, if (expenseDown) e.negate() else e, x))
                }.onSuccess { result = it }.onFailure { if (it !is AuthException.SignedOut) error = it.message }
                busy = false
            }
        })
        result?.let { r ->
            Section(tx("Resultado", "Result")) {
                AmountLine(tx("Margen actual", "Current margin"), r.current?.strategicMargin)
                AmountLine(tx("Margen con el cambio", "Margin with the change"), r.scenario?.strategicMargin, emphasize = true)
                AmountLine(tx("Diferencia", "Difference"), r.delta?.strategicMargin, sign = if ((r.delta?.strategicMargin?.signum() ?: 0) >= 0) MoneyFormat.Sign.INCOME else MoneyFormat.Sign.NONE)
                r.scenario?.recommendation?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2) }
            }
        }
        FinancialDisclaimer()
    }
}

/** F8 — VIP monthly review. It needs history; until then the backend answers BASELINE. */
@Composable
fun MonthlyReviewScreen(model: AppModel, nav: Navigator) {
    var month by remember { mutableStateOf(YearMonth.now()) }
    val review = rememberLoad(model, month) { model.api.monthlyReview(month.toString()) }
    DetailScaffold(tx("Revisión mensual", "Monthly review"), nav::back) {
        MonthPicker(month, { month = it })
        LoadContent(review) { r ->
            if (r.status == "BASELINE") StatusBanner(BannerTone.INFO, r.headline ?: tx("Todavía sin comparación", "No comparison yet"), r.summary ?: tx("DINCR necesita más historia de este mes para comparar.", "DINCR needs more history for this month to compare."))
            else {
                r.headline?.let { Text(it, style = MaterialTheme.typography.titleLarge, color = Dincr.colors.text) }
                r.summary?.let { Text(it, style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text2) }
                if (r.scorecard.isNotEmpty()) Section(tx("Indicadores", "Indicators")) {
                    r.scorecard.forEach { line ->
                        val trend = when (line.trend) { "improved" -> tx("mejoró", "improved"); "declined" -> tx("empeoró", "declined"); else -> tx("igual", "unchanged") }
                        if (line.unit == "CRC") AmountLine("${line.label.orEmpty()} · $trend", line.current?.toBigDecimal()) else InfoLine(line.label.orEmpty(), "${line.current ?: "—"} · $trend")
                    }
                }
            }
            r.nextMonth?.let { next ->
                Section(tx("El próximo mes", "Next month")) {
                    next.title?.let { Text(it, style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text) }
                    next.amount?.takeIf { it.signum() > 0 }?.let { AmountLine(tx("Monto", "Amount"), it) }
                    next.rationale?.let { Caption(it) }
                }
            }
        }
        FinancialDisclaimer()
    }
}

/** F9 — VIP proactive advisor ("DINCR hoy"). */
@Composable
fun TodayScreen(model: AppModel, nav: Navigator) {
    val today = rememberLoad(model) { model.api.dincrToday() }
    DetailScaffold(tx("DINCR hoy", "DINCR today"), nav::back) {
        LoadContent(today) { t ->
            val a = t.advisor
            when {
                t.isBaseline -> {
                    // No earlier observation yet: changes can't be compared, but the current situation is known.
                    StatusBanner(BannerTone.INFO, tx("Aprendiendo tu punto de partida", "Learning your starting point"), a.message ?: tx("DINCR necesita unos días de historia para avisarte de cambios.", "DINCR needs a few days of history to alert you about changes."))
                    val current = t.currentAlerts.orEmpty()
                    if (current.isNotEmpty()) {
                        SectionTitle(tx("Tu situación actual", "Your current situation"))
                        current.forEach { alert ->
                            val tone = if (alert.severity in setOf("critical", "high")) BannerTone.WARNING else BannerTone.INFO
                            StatusBanner(tone, alert.title.orEmpty(), listOfNotNull(alert.context, alert.action).filter { it.isNotBlank() }.joinToString(" "))
                        }
                    } else if (t.currentAlerts != null) {
                        EmptyState(Icons.Rounded.NotificationsActive, tx("Nada urgente hoy", "Nothing urgent today"), tx("Tu situación actual no tiene avisos.", "Your current situation has no alerts."))
                    }
                }
                a.alerts.isEmpty() -> EmptyState(Icons.Rounded.NotificationsActive, tx("Todo en orden", "All good"), a.message ?: tx("No hay cambios que requieran tu atención.", "Nothing needs your attention."))
                else -> a.alerts.forEach { alert ->
                    val tone = when (alert.severity) { "critical", "high" -> BannerTone.WARNING; "success" -> BannerTone.INFO; else -> BannerTone.INFO }
                    StatusBanner(tone, alert.title.orEmpty(), alert.explanation.orEmpty())
                    alert.action?.let { action ->
                        val route = when (action.route?.trim('/')) { "debts" -> "debts"; "goals" -> "goals"; "budget" -> "budget"; "finance", "movements" -> "movements"; "situation" -> "situation"; else -> null }
                        val label = action.label
                        if (route != null && label != null) TextButton({ nav.open(route) }) { Text(label, color = Dincr.colors.tint) }
                    }
                }
            }
        }
        FinancialDisclaimer()
    }
}

/** F5 — VIP projections from the command center. */
@Composable
fun ProjectionsScreen(model: AppModel, nav: Navigator) {
    val center = rememberLoad(model) { model.api.commandCenter() }
    DetailScaffold(tx("Proyecciones", "Projections"), nav::back) {
        LoadContent(center) { c ->
            if (c.projections.isEmpty()) EmptyState(Icons.Rounded.Timeline, tx("Sin proyecciones todavía", "No projections yet"), tx("Registrá ingresos, gastos y deudas para proyectar.", "Record income, expenses and debts to project."))
            c.projections.sortedBy { it.months ?: 0 }.forEach { p ->
                Section(tx("En ${p.months} ${if (p.months == 1) "mes" else "meses"}", "In ${p.months} month${if (p.months == 1) "" else "s"}")) {
                    AmountLine(tx("Patrimonio neto", "Net worth"), p.netWorth, emphasize = true)
                    AmountLine(tx("Efectivo", "Cash"), p.cash)
                    AmountLine(tx("Deuda", "Debt"), p.debt)
                    if (p.confidence == "low") Caption(tx("Confianza baja: faltan datos.", "Low confidence: data is missing."))
                }
            }
            c.debtPlanner?.recommended?.let { plan ->
                Section(tx("Plan de deudas recomendado", "Recommended debt plan")) {
                    plan.target?.let { Text(it, style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text) }
                    AmountLine(tx("Pago mensual", "Monthly payment"), plan.monthlyToTarget)
                    plan.months?.let { InfoLine(tx("Meses", "Months"), it.toString()) }
                    AmountLine(tx("Intereses estimados", "Estimated interest"), plan.interest)
                }
            }
        }
        FinancialDisclaimer()
    }
}

/** E12 — VIP aguinaldo from the CCSS payroll notices in the connected mailbox (always colones). */
@Composable
fun AguinaldoScreen(model: AppModel, nav: Navigator) {
    // 409 = no mailbox connected: that is a state to explain, not an error.
    val aguinaldo = rememberLoad(model) {
        try { model.api.aguinaldo() } catch (error: ApiError) { if (error.status == 409) null else throw error }
    }
    var syncing by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val crc = Dincr.money.copy(currency = "CRC")
    DetailScaffold(tx("Aguinaldo", "Aguinaldo"), nav::back) {
        // The backend pauses /vip/aguinaldo with vip_intelligence (core/feature_flags.py), not with mail automation.
        if (!model.isOn(OpsFlag.VIP_INTELLIGENCE)) { FeaturePaused(model, OpsFlag.VIP_INTELLIGENCE); return@DetailScaffold }
        LoadContent(aguinaldo) { a ->
            if (a == null) {
                EmptyState(Icons.Rounded.AutoAwesome, tx("Conectá tu correo", "Connect your mail"),
                    tx("El aguinaldo se estima con las órdenes patronales de la CCSS que llegan a tu correo.", "The aguinaldo is estimated from the CCSS payroll notices in your mail.")) {
                    if (model.isOn(OpsFlag.GMAIL_AUTOMATION)) DincrPrimaryButton(tx("Conectar correo", "Connect mail"), { nav.open("mail") })
                }
            } else {
                DincrCard {
                    Column {
                        Text(tx("Aguinaldo acumulado", "Accrued aguinaldo"), style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2)
                        Text(a.accruedAguinaldo?.let { crc.format(it) } ?: "—", style = MaterialTheme.typography.displaySmall, color = Dincr.colors.text)
                        InfoLine(tx("Salarios considerados", "Salaries counted"), a.earnedSalaryTotal?.let { crc.format(it) } ?: "—")
                        a.period?.let { InfoLine(tx("Período", "Period"), "${dateLabel(it.start)} – ${dateLabel(it.end)}") }
                    }
                }
                if (a.status == "NO_SALARY_DATA") StatusBanner(BannerTone.INFO, tx("Sin órdenes patronales", "No payroll notices"), tx("Todavía no encontramos órdenes de la CCSS en tu correo.", "We haven’t found CCSS payroll notices in your mail yet."))
                if (a.missingMonths.isNotEmpty()) StatusBanner(BannerTone.INFO, tx("Faltan meses", "Missing months"), a.missingMonths.joinToString(", "))
                a.months.forEach { m -> InfoLine(m.month.orEmpty(), m.totalEarned?.let { crc.format(it) } ?: "—") }
            }
        }
        // Syncing reads the mailbox: offered only while mail automation is on.
        if (model.isOn(OpsFlag.GMAIL_AUTOMATION)) DincrPrimaryButton(tx("Sincronizar y recalcular", "Sync and recalculate"), loading = syncing, onClick = {
            syncing = true
            scope.launch {
                model.load(tx("No pudimos sincronizar tu correo.", "We couldn’t sync your mail.")) { model.api.syncMail() }
                    .onFailure { if (it !is AuthException.SignedOut) model.showNotice(it.message.orEmpty()) }
                aguinaldo.reload(); syncing = false
            }
        })
        Caption(tx("Estimación según la ley costarricense; confirmala con tu patrono.", "Estimate under Costa Rican law; confirm it with your employer."))
    }
}
