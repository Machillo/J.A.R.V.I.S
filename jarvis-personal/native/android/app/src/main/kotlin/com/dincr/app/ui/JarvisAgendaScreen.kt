package com.dincr.app.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.widthIn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.CalendarMonth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.dincr.app.AppModel
import com.dincr.app.tx
import com.dincr.data.AppLanguage
import com.dincr.data.JarvisAgenda
import com.dincr.design.Dincr
import com.dincr.design.DincrCard
import com.dincr.design.DincrPrimaryButton
import com.dincr.design.EmptyState
import com.dincr.design.generated.DincrSpacing
import java.time.LocalDate
import java.time.format.DateTimeFormatter
import java.util.Locale

/**
 * JARVIS agenda (recovery roadmap J2): the Owner's upcoming events for the next 45 days, the
 * historical "Próximos eventos" of JARVIS, as a native list grouped by day. Events are created through
 * the chat, as they always were: "Agendar con JARVIS" opens it; nothing here edits data. The screen
 * reloads every time it is shown, so an event confirmed in the chat is there on return. iOS:
 * `JarvisAgendaView`.
 */
@Composable
fun JarvisAgendaScreen(model: AppModel, nav: Navigator) {
    val agenda = rememberLoad(model) { model.api.jarvisUpcomingEvents() }
    val schedule = @Composable {
        DincrPrimaryButton(tx("Agendar con JARVIS", "Schedule with JARVIS"), { nav.push("jarvis/chat") }, Modifier.fillMaxWidth().testTag("jarvis.agenda.schedule"))
    }
    DetailScaffold(tx("Agenda", "Calendar"), onBack = nav::back) {
        LoadContent(agenda, rows = 3) { events ->
            if (events.isEmpty()) {
                Column(Modifier.testTag("jarvis.agenda.empty"), verticalArrangement = Arrangement.spacedBy(DincrSpacing.s4)) {
                    EmptyState(Icons.Rounded.CalendarMonth, tx("No hay compromisos próximos", "No upcoming commitments"),
                        tx("Pedile a JARVIS que agende algo, por ejemplo “Agendá dentista el 10 de octubre a las 3pm”.",
                            "Ask JARVIS to schedule something, for example “Agendá dentista el 10 de octubre a las 3pm”."))
                    schedule()
                }
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s4)) {
                    schedule()
                    Caption(tx("Próximos ${JarvisAgenda.DAYS} días", "Next ${JarvisAgenda.DAYS} days"))
                    JarvisAgenda.days(events).forEach { day -> DayCard(day) }
                }
            }
        }
    }
}

/** One day: its date, then each event with its time when it has one. */
@Composable
private fun DayCard(day: JarvisAgenda.Day) {
    DincrCard(Modifier.widthIn(max = ContentMaxWidth)) {
        Column(verticalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
            Text(dayLabel(day), style = MaterialTheme.typography.titleMedium, color = Dincr.colors.text, modifier = Modifier.semantics { heading() })
            day.events.forEach { event ->
                Row(Modifier.fillMaxWidth().testTag("jarvis.agenda.event"), verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(DincrSpacing.s3)) {
                    Text(event.time ?: "—", style = MaterialTheme.typography.bodyMedium.copy(fontWeight = FontWeight.SemiBold),
                        color = if (event.time == null) Dincr.colors.textMuted else Dincr.colors.tint, modifier = Modifier.widthIn(min = 48.dp))
                    Text(event.title, style = MaterialTheme.typography.bodyLarge, color = Dincr.colors.text)
                }
            }
        }
    }
}

/** "Hoy", "Mañana" or the full date in the session language; the stored text if it is not a date. */
private fun dayLabel(day: JarvisAgenda.Day): String {
    val date = day.events.firstOrNull()?.date ?: return day.day
    val today = LocalDate.now()
    if (date == today) return tx("Hoy", "Today")
    if (date == today.plusDays(1)) return tx("Mañana", "Tomorrow")
    val locale = if (AppLanguage.current() == AppLanguage.SPANISH) Locale.forLanguageTag("es-CR") else Locale.US
    return date.format(DateTimeFormatter.ofPattern("EEEE d 'de' MMMM", locale).takeIf { locale != Locale.US } ?: DateTimeFormatter.ofPattern("EEEE, MMMM d", locale))
        .replaceFirstChar { it.titlecase(locale) }
}
