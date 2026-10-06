package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AttentionItem
import com.dincr.data.AttentionList
import com.dincr.data.MessageKind
import com.dincr.data.OpsFlag
import com.dincr.data.ProactiveAdvisor
import com.dincr.design.Dincr
import com.dincr.design.DincrMessage
import com.dincr.design.SkeletonBlock
import com.dincr.design.generated.DincrSpacing

/**
 * "Para atender" on Hoy (UX-5): the first items of [AttentionList.today] and "Ver todas" when there
 * are more. With nothing to show the section is left out entirely (never an empty or "all clear"
 * block). VIP and the Owner share it. iOS: `AttentionSection`.
 */
@Composable
fun AttentionSection(today: AttentionList.Today, nav: Navigator) {
    if (today.isEmpty) return
    Column(Modifier.testTag("home.attention"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s2)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            SectionTitle(tx("Para atender", "Needs attention"), Modifier.weight(1f))
            if (today.showsSeeAll) {
                TextButton({ nav.open("attention") }, Modifier.testTag("home.attention.all")) {
                    Text(tx("Ver todas", "See all"), color = Dincr.colors.tint)
                }
            }
        }
        today.visible.forEach { AttentionRow(it, nav, "home.attention") }
    }
}

/**
 * One item: the message in its UX-1 meaning, "change since the last observation" for the advisor's
 * items, and a link only when the item has a real destination.
 */
@Composable
fun AttentionRow(item: AttentionItem, nav: Navigator, tagPrefix: String = "attention") {
    Column(Modifier.testTag("$tagPrefix.item.${item.source.key}"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s1)) {
        DincrMessage(item.kind, item.title, item.message)
        if (item.isChange) {
            Text(tx("Cambio desde la última observación", "Change since the last check"), style = MaterialTheme.typography.bodySmall,
                color = Dincr.colors.textMuted, modifier = Modifier.padding(horizontal = DincrSpacing.s4))
        }
        item.destination?.let { destination ->
            TextButton({ nav.open(destination.route) }, Modifier.testTag("$tagPrefix.link.${destination.key}")) {
                Text("${destination.title} ›", color = Dincr.colors.tint)
            }
        }
    }
}

/**
 * "Ver todas": every item, uncapped, with the proactive advisor's changes (D-3). Read-only: both
 * sources are GETs. If the advisor can't be read, the command center's items still show and the
 * failure is said as a technical problem, never as "nothing pending".
 */
@Composable
fun AttentionScreen(model: AppModel, nav: Navigator) {
    val center = rememberLoad(model, fallback = tx("No pudimos cargar lo que necesita tu atención.", "We couldn’t load what needs your attention.")) { model.api.commandCenter() }
    // The advisor's own state: an account that can't read it right now (paused, or not in its plan)
    // simply doesn't see its changes; only a real failure is a technical problem.
    val advisor by produceState<AdvisorState>(AdvisorState.Loading, model) {
        value = model.load(tx("No pudimos revisar los cambios recientes.", "We couldn’t check recent changes.")) { model.api.proactiveAdvisor() }
            .fold({ AdvisorState.Ready(it) }, { if (AttentionList.isUnavailable(it)) AdvisorState.Unavailable else AdvisorState.Failed })
    }
    DetailScaffold(tx("Para atender", "Needs attention"), nav::back) {
        Column(Modifier.testTag("attention.list"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
            LoadContent(center, rows = 3) { c ->
                val items = AttentionList.items(c, (advisor as? AdvisorState.Ready)?.value, model.isOn(OpsFlag.GMAIL_AUTOMATION))
                items.forEach { AttentionRow(it, nav) }
                when (advisor) {
                    AdvisorState.Loading -> SkeletonBlock(rows = 1)
                    AdvisorState.Unavailable -> Unit
                    AdvisorState.Failed -> Column(Modifier.testTag("attention.advisor.unavailable")) {
                        DincrMessage(MessageKind.TECHNICAL_ERROR, tx("No pudimos revisar los cambios recientes", "We couldn’t check recent changes"),
                            tx("Lo de arriba sigue vigente. Probá de nuevo en un momento.", "What’s above still applies. Try again in a moment."))
                    }
                    // Both sources answered: only now is "nothing" a fact.
                    is AdvisorState.Ready -> if (items.isEmpty()) {
                        Text(tx("No hay nada para atender en este momento.", "There’s nothing that needs attention right now."),
                            style = MaterialTheme.typography.bodyMedium, color = Dincr.colors.text2, modifier = Modifier.testTag("attention.none"))
                    }
                }
            }
        }
    }
}

private sealed interface AdvisorState {
    data object Loading : AdvisorState
    data object Unavailable : AdvisorState
    data object Failed : AdvisorState
    data class Ready(val value: ProactiveAdvisor) : AdvisorState
}

private val AttentionItem.Destination.title: String
    get() = when (this) {
        AttentionItem.Destination.REVIEW -> tx("Revisar avisos del correo", "Review mail notices")
        AttentionItem.Destination.DEBTS -> tx("Ver deudas", "See debts")
        AttentionItem.Destination.SALVAVIDAS -> tx("Ver Salvavidas", "See Salvavidas")
        AttentionItem.Destination.INCOME_BASE -> tx("Ver ingresos y base", "See income and base")
        AttentionItem.Destination.STRATEGY -> tx("Ver tu plan del mes", "See your plan for the month")
        AttentionItem.Destination.MOVEMENTS -> tx("Ver movimientos", "See transactions")
        AttentionItem.Destination.MONTHLY_REVIEW -> tx("Ver revisión del mes", "See monthly review")
    }
