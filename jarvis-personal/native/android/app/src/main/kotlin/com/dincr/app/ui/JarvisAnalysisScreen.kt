package com.dincr.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.FinancialEngineReport
import com.dincr.data.NetWorthReport
import com.dincr.data.OwnerAnalysis
import com.dincr.data.TransactionAnalysis
import com.dincr.design.BannerTone
import com.dincr.design.CategoryBars
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.IncomeExpenseBars
import com.dincr.design.MoneyText
import com.dincr.design.StatusBanner
import com.dincr.design.generated.DincrSpacing
import java.math.BigDecimal
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope

/**
 * JARVIS → Análisis financiero (Owner only; parity with the historical web Finanzas tab): spending
 * distribution, income vs expenses, expenses by month, net worth and the financial engine. Reached
 * only through [JarvisSectionScreen] (Owner role); the backend still decides each request. Built
 * from the existing native components; every figure is the backend's.
 */
@Composable
fun JarvisAnalysisScreen(model: AppModel, nav: Navigator) {
    val data = rememberLoad(model) {
        coroutineScope {
            val transactions = async { model.api.transactionAnalysis() }
            val netWorth = async { model.api.netWorth() }
            val engine = async { model.api.financialEngine() }
            OwnerAnalysis(transactions.await(), netWorth.await(), engine.await())
        }
    }
    DetailScaffold(tx("Análisis financiero", "Financial analysis"), onBack = nav::back) {
        LoadContent(data) { analysis ->
            NetWorthSection(analysis.netWorth)
            HealthSection(analysis.engine)
            SpendingSection(analysis.transactions)
        }
    }
}

@Composable
private fun NetWorthSection(n: NetWorthReport) {
    DincrCard {
        Column(Modifier.testTag("analysis.networth"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
            Text(tx("Patrimonio neto", "Net worth"), style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2)
            MoneyText(n.netWorth, style = MaterialTheme.typography.displaySmall)
            AmountLine(tx("Activos", "Assets"), n.assets?.assetsTotal)
            AmountLine(tx("Ahorros y cuentas", "Savings and accounts"), n.assets?.savingsTotal)
            AmountLine(tx("Inversiones", "Investments"), n.assets?.investmentsTotal)
            AmountLine(tx("Deudas", "Debts"), n.liabilities?.debtTotal)
            n.change?.amount?.let { AmountLine(tx("Cambio desde el último registro", "Change since the last record"), it) }
            n.interpretation?.let { Caption(it) }
            n.priority?.let { Caption(it) }
        }
    }
}

@Composable
private fun HealthSection(e: FinancialEngineReport) {
    Section(tx("Salud financiera", "Financial health")) {
        e.health?.score?.let { score ->
            InfoLine(tx("Puntaje", "Score"), "${score.toInt()} / 100" + (e.health?.level?.let { " · " + healthLevel(it) } ?: ""))
            ProgressLine(score / 100.0, tx("Salud financiera ${score.toInt()} de 100", "Financial health ${score.toInt()} of 100"))
        }
        e.forecast?.let { f ->
            AmountLine(tx("Cierre de mes previsto", "Expected month-end balance"), f.projectedEndBalance, emphasize = true)
            f.alert?.message?.let { StatusBanner(if (f.alert?.level == "high") BannerTone.WARNING else BannerTone.INFO, tx("Pronóstico", "Forecast"), it) }
        }
        e.emergencyFund?.let { f ->
            AmountLine(tx("Salvavidas", "Emergency fund"), f.current)
            AmountLine(tx("Base mensual", "Monthly base"), f.monthlyBase)
            f.coverageMonths?.let { InfoLine(tx("Cobertura", "Coverage"), tx("${it.stripTrailingZeros().toPlainString()} meses", "${it.stripTrailingZeros().toPlainString()} months")) }
        }
        e.debts?.recommended?.priorityDebt?.let { d ->
            AmountLine(tx("Deuda prioritaria", "Priority debt") + (d.name?.let { " · $it" } ?: ""), d.remainingAmount)
        }
        e.recommendations.forEach { Text("• $it", style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2) }
    }
}

private fun healthLevel(level: String) = when (level) {
    "strong" -> tx("sólida", "strong"); "stable" -> tx("estable", "stable"); "fragile" -> tx("frágil", "fragile"); "critical" -> tx("crítica", "critical"); else -> level
}

@Composable
private fun SpendingSection(t: TransactionAnalysis) {
    t.spendingBreakdown?.takeIf { it.categories.isNotEmpty() }?.let { b ->
        Section(tx("Distribución de gastos", "Spending distribution") + (b.period?.label?.let { " · $it" } ?: "")) {
            AmountLine(tx("Total", "Total"), b.total, emphasize = true)
            CategoryBars(b.categories.map { (it.category ?: tx("Sin categoría", "Uncategorized")) to (it.total ?: BigDecimal.ZERO) }, limit = 8)
        }
    }
    if (t.monthlyFlow.isNotEmpty()) Section(tx("Ingresos y gastos", "Income and expenses")) {
        IncomeExpenseBars(t.monthlyFlow.takeLast(6).map { Triple(shortMonth(it.month.orEmpty()), it.income ?: BigDecimal.ZERO, it.expenses ?: BigDecimal.ZERO) })
    }
    if (t.expensesByMonth.isNotEmpty()) Section(tx("Gastos por mes", "Expenses by month")) { MonthBars(t.expensesByMonth.takeLast(12)) }
}

/** Expenses per month in calendar order (the bars of the web tab), labelled directly. */
@Composable
private fun MonthBars(months: List<TransactionAnalysis.MonthTotal>) {
    val top = months.maxOfOrNull { it.total?.toDouble() ?: 0.0 }?.coerceAtLeast(1.0) ?: 1.0
    Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
        months.forEach { m ->
            Column(Modifier.semantics(mergeDescendants = true) {}) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(shortMonth(m.month.orEmpty()) + " " + m.month.orEmpty().take(4), style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text)
                    MoneyText(m.total, style = MaterialTheme.typography.bodyMedium)
                }
                Box(Modifier.padding(top = 4.dp).fillMaxWidth(((m.total?.toDouble() ?: 0.0) / top).toFloat().coerceIn(0.02f, 1f)).height(6.dp).background(Dincr.colors.chartExpense, CircleShape))
            }
        }
    }
}
