package com.dincr.app.ui

import androidx.compose.material.icons.rounded.PieChart
import androidx.compose.foundation.layout.Box
import com.dincr.design.CompositionDonut
import com.dincr.data.Debt
import com.dincr.data.DebtComposition
import com.dincr.data.Composition
import androidx.compose.ui.unit.dp
import androidx.compose.foundation.layout.heightIn
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.Modifier
import androidx.compose.material3.TextButton
import androidx.compose.material.icons.rounded.AccountBalance
import androidx.compose.foundation.layout.Column
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.Summarize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
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
import kotlinx.coroutines.launch

/** B16 — every advisory screen says what DINCR is and is not. */
@Composable
fun FinancialDisclaimer() {
    Caption(tx("DINCR orienta con tus datos; no es asesoría financiera, legal ni tributaria. Revisá las decisiones importantes con un profesional.",
        "DINCR guides you with your data; it is not financial, legal or tax advice. Check important decisions with a professional."))
}

/**
 * UX-13 — Movimientos → Análisis: the monthly summary (every plan) and, FA-1, the financial analysis
 * in plain words (VIP and the Owner; below VIP the row stays visible, locked, and opens Suscripción).
 */
@Composable
fun AnalysisScreen(model: AppModel, nav: Navigator) {
    val profile by model.profile.collectAsStateWithLifecycle()
    val plan = profile?.planTier ?: PlanTier.FREE
    val vipOn = model.isOn(OpsFlag.VIP_INTELLIGENCE)
    DetailScaffold(tx("Análisis", "Analysis"), nav::back) {
        if (plan == PlanTier.VIP && !vipOn) FeaturePaused(model, OpsFlag.VIP_INTELLIGENCE)
        DincrCard {
            Column {
                NavRow(Icons.Rounded.Summarize, tx("Resumen del mes", "Monthly summary"), tx("Ingresos, gastos y metas por mes", "Income, expenses and goals by month")) { nav.open("monthly") }
                // FA-1: the financial analysis in plain words (VIP and the Owner, whose plan is VIP); the
                // Owner's full historical analysis stays in JARVIS.
                Box(Modifier.testTag("analysis.financial")) {
                    if (plan != PlanTier.VIP) {
                        LockedRow(Icons.Rounded.PieChart, tx("Análisis financiero", "Financial analysis"), PlanTier.VIP, nav)
                    } else {
                        NavRow(Icons.Rounded.PieChart, tx("Análisis financiero", "Financial analysis"), tx("Tus números explicados en palabras simples", "Your numbers explained in simple words")) { nav.open("financialAnalysis") }
                    }
                }
            }
        }
    }
}

/**
 * UX-13 / §15 PR 8 — the Patrimonio tab: what you have and what you owe. Cuentas: the accounts DINCR
 * detected in bank notices (VIP and the Owner, locked below). Deudas: how the active debts make up
 * what is owed, from Plan → Deudas' balances (every plan). The mail connections live in Perfil,
 * Proyecciones and Escenarios in Plan (WE-1). No net worth figure until P0.9 (K-3), no balance
 * invented. iOS: `WealthHubView`.
 * B17: pulling down reads the plan, the switches and the debts again; a failed read keeps what the card
 * showed ([LoadHandle.refresh]).
 */
@Composable
fun WealthScreen(model: AppModel, nav: Navigator) {
    val profile by model.profile.collectAsStateWithLifecycle()
    val plan = profile?.planTier ?: PlanTier.FREE
    val debts = rememberLoad(model) { model.api.debts() }
    RefreshableTab(model, tx("Patrimonio", "Wealth"), extra = debts.refresh) {
        SectionTitle(tx("Cuentas", "Accounts"))
        DincrCard {
            Column {
                // The screens say themselves when the mail switch pauses them (as in Perfil).
                if (plan != PlanTier.VIP) {
                    LockedRow(Icons.Rounded.AccountBalance, tx("Cuentas", "Accounts"), PlanTier.VIP, nav)
                } else {
                    NavRow(Icons.Rounded.AccountBalance, tx("Cuentas", "Accounts"), tx("Bancos y cuentas detectados en tus avisos", "Banks and accounts found in your notices")) { nav.open("accounts") }
                }
            }
        }
        SectionTitle(tx("Deudas", "Debts"))
        WealthDebtsCard(debts, nav)
    }
}

/**
 * §15 PR 8 — what is owed, by debt, from the balances in Plan → Deudas ([DebtComposition]); managed
 * there. An unknown balance is listed as unknown and no share or total is drawn from it.
 */
@Composable
private fun WealthDebtsCard(debts: LoadHandle<List<Debt>>, nav: Navigator) {
    DincrCard {
        Column(Modifier.testTag("wealth.debts")) {
            LoadContent(debts) { list ->
                val composition = DebtComposition.of(list)
                if (composition.status == Composition.Status.EMPTY) {
                    Text(tx("No tenés deudas activas registradas.", "You have no active debts recorded."), style = MaterialTheme.typography.bodyMedium,
                        color = Dincr.colors.text2, modifier = Modifier.testTag("wealth.debts.none"))
                } else {
                    Column(Modifier.testTag("wealth.debts.composition")) { CompositionDonut(tx("Lo que debés, por deuda", "What you owe, by debt"), composition) }
                }
            }
            TextButton({ nav.open("debts") }, Modifier.heightIn(min = 48.dp).testTag("wealth.debts.manage")) {
                Text(tx("Administrar en Plan › Deudas", "Manage in Plan › Debts"), color = Dincr.colors.tint)
            }
        }
    }
}

/** Below its plan an entry stays visible, locked, and opens Suscripción (as the Plan tab's rows). */
@Composable
private fun LockedRow(icon: androidx.compose.ui.graphics.vector.ImageVector, title: String, minimum: PlanTier, nav: Navigator) {
    val name = if (minimum == PlanTier.VIP) "VIP" else "Basic"
    NavRow(icon, title, tx("Disponible desde $name", "Available from $name"), badge = name) { nav.open("plans") }
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
    var choice by remember { mutableStateOf(ScenarioChoice.GENERAL) }
    val scope = rememberCoroutineScope()
    DetailScaffold(tx("Escenarios", "Scenarios"), nav::back) {
        ScenarioChoicePicker(choice) { choice = it }
        if (choice != ScenarioChoice.GENERAL) {
            DebtScenarioForm(model, choice)
            FinancialDisclaimer()
            return@DetailScaffold
        }
        Caption(tx("Probá cambios sin guardar nada: DINCR calcula cuánto te quedaría libre cada mes.", "Try changes without saving anything: DINCR shows how much you’d have left each month."))
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
                AmountLine(tx("Te queda libre al mes hoy", "Left each month today"), r.current?.strategicMargin)
                AmountLine(tx("Te quedaría libre con el cambio", "Left each month with the change"), r.scenario?.strategicMargin, emphasize = true)
                AmountLine(tx("Diferencia", "Difference"), r.delta?.strategicMargin, sign = if ((r.delta?.strategicMargin?.signum() ?: 0) >= 0) MoneyFormat.Sign.INCOME else MoneyFormat.Sign.NONE)
                r.scenario?.recommendation?.let { Text(it, style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2) }
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
    val canRead = model.profile.collectAsStateWithLifecycle().value?.canReadMail == true
    DetailScaffold(tx("Aguinaldo", "Aguinaldo"), nav::back) {
        // The backend pauses /vip/aguinaldo with vip_intelligence (core/feature_flags.py), not with mail automation.
        if (!model.isOn(OpsFlag.VIP_INTELLIGENCE)) { FeaturePaused(model, OpsFlag.VIP_INTELLIGENCE); return@DetailScaffold }
        LoadContent(aguinaldo) { a ->
            if (a == null) {
                EmptyState(Icons.Rounded.AutoAwesome, tx("Conectá tu correo", "Connect your mail"),
                    tx("El aguinaldo se estima con las órdenes patronales de la CCSS que llegan a tu correo.", "The aguinaldo is estimated from the CCSS payroll notices in your mail.")) {
                    if (model.isOn(OpsFlag.GMAIL_AUTOMATION) && canRead) DincrPrimaryButton(tx("Conectar correo", "Connect mail"), { nav.open("mail") })
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
        if (model.isOn(OpsFlag.GMAIL_AUTOMATION) && canRead) DincrPrimaryButton(tx("Sincronizar y recalcular", "Sync and recalculate"), loading = syncing, onClick = {
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
