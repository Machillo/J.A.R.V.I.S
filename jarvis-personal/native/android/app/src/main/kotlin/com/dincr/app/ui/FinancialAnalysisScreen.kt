package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.FinancialAnalysis
import com.dincr.data.FinancialReading
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.IncomeExpenseBars
import com.dincr.design.generated.DincrSpacing

/**
 * FA-1 — Movimientos → Análisis → Análisis financiero (VIP and the Owner): the user's last twelve
 * months in plain words, for people who do not know finance. A normal month (what is left, how much is
 * saved and how much goes to debts, each with one line saying what it means), the months side by side,
 * and where this month already spends more than usual. The backend counts (`/vip/financial-analysis`);
 * [FinancialReading] writes the sentences. The Owner's full historical analysis stays in JARVIS.
 * iOS twin: `FinancialAnalysisView.swift`.
 */
@Composable
fun FinancialAnalysisScreen(model: AppModel, nav: Navigator) {
    val data = rememberLoad(model) { model.api.financialAnalysis() }
    DetailScaffold(tx("Análisis financiero", "Financial analysis"), nav::back) {
        LoadContent(data) { analysis -> FinancialAnalysisContent(analysis) }
    }
}

@Composable
private fun FinancialAnalysisContent(analysis: FinancialAnalysis) {
    val format = Dincr.money
    val normal = FinancialReading.normal(analysis)
    if (normal != null) {
        ReadingCard(tx("Tu mes normal", "Your normal month"), FinancialReading.leftSentence(normal, format), FinancialReading.leftExplanation(normal, format), "analysis.financial.left")
        FinancialReading.savedSentence(normal)?.let {
            ReadingCard(tx("¿Cuánto guardás?", "How much do you save?"), it, FinancialReading.savedExplanation(), "analysis.financial.saved")
        }
        FinancialReading.debtSentence(normal)?.let {
            ReadingCard(tx("¿Cuánto se va a deudas?", "How much goes to debts?"), it, FinancialReading.debtExplanation(), "analysis.financial.debts")
        }
    } else {
        ReadingCard(tx("Tu mes normal", "Your normal month"),
            tx("Todavía no hay un mes completo con ingresos y gastos registrados.", "There is no complete month with income and expenses recorded yet."),
            tx("Cuando lo haya, acá vas a ver cuánto te sobra en un mes normal, cuánto guardás y cuánto se va a deudas.",
                "When there is, you will see here how much is left in a normal month, how much you save and how much goes to debts."),
            "analysis.financial.none")
    }
    val months = FinancialReading.chartMonths(analysis)
    if (months.isNotEmpty()) {
        DincrCard {
            Column(Modifier.testTag("analysis.financial.months"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
                SectionTitle(tx("Mes a mes", "Month by month"))
                Text(tx("Lo que entró y lo que salió cada mes. Los meses sin nada registrado no aparecen.",
                    "What came in and went out each month. Months with nothing recorded are not shown."),
                    style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2)
                IncomeExpenseBars(months.map { Triple(shortMonth(it.month), it.income, it.expenses) })
            }
        }
    }
    if (FinancialReading.canCompare(analysis)) RisesCard(FinancialReading.rises(analysis))
}

/** A title, the sentence that answers it, and one line saying what it means. */
@Composable
private fun ReadingCard(title: String, sentence: String, explanation: String, tag: String) {
    DincrCard {
        Column(Modifier.fillMaxWidth().testTag(tag), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
            Text(title, style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2, modifier = Modifier.semantics { heading() })
            Text(sentence, style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text)
            Caption(explanation)
        }
    }
}

/** "¿En qué gastás más de lo normal este mes?": only categories already above their average. */
@Composable
private fun RisesCard(rises: List<FinancialAnalysis.Category>) {
    val format = Dincr.money
    DincrCard {
        Column(Modifier.fillMaxWidth().testTag("analysis.financial.rises"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
            Text(tx("¿En qué gastás más de lo normal este mes?", "Where are you spending more than usual this month?"),
                style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2, modifier = Modifier.semantics { heading() })
            if (rises.isEmpty()) {
                Text(tx("En nada, por ahora: ninguna categoría pasa de lo que gastás normalmente.", "Nothing so far: no category is above what you usually spend."),
                    style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text)
            } else {
                rises.forEach { Text(FinancialReading.riseLine(it, format), style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text) }
            }
            Caption(tx("Comparamos este mes con el promedio de tus últimos meses. El mes todavía no termina.",
                "We compare this month with the average of your last months. The month is not over yet."))
        }
    }
}
