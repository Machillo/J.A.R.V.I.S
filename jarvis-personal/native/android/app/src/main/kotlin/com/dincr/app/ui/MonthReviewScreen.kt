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
import com.dincr.data.MonthReview
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.generated.DincrSpacing
import java.time.LocalDate

/**
 * RV-1 — Movimientos → Análisis → Revisión del mes (every plan): the month that just closed in three
 * short cards, easy to read, from the same summary Resumen del mes counts ([MonthReview]).
 * iOS twin: `MonthReviewView.swift`.
 */
@Composable
fun MonthReviewScreen(model: AppModel, nav: Navigator) {
    val data = rememberLoad(model) {
        val (closed, before) = MonthReview.closedMonths(LocalDate.now())
        // The month before is optional: without it there is no comparison.
        val previous = runCatching { model.api.monthlySummary(before) }.getOrNull()
        MonthReview.cards(model.api.monthlySummary(closed), previous, model.moneyFormat)
    }
    DetailScaffold(tx("Revisión del mes", "Monthly review"), nav::back) {
        LoadContent(data) { cards ->
            cards.forEachIndexed { index, card ->
                DincrCard {
                    Column(Modifier.fillMaxWidth().testTag("review.card.$index"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
                        Text(card.title, style = MaterialTheme.typography.labelLarge, color = Dincr.colors.text2, modifier = Modifier.semantics { heading() })
                        card.lines.forEachIndexed { line, text ->
                            Text(text, style = if (line == 0) MaterialTheme.typography.titleMedium else MaterialTheme.typography.bodyMedium,
                                color = if (line == 0) Dincr.colors.text else Dincr.colors.text2)
                        }
                    }
                }
            }
        }
    }
}
