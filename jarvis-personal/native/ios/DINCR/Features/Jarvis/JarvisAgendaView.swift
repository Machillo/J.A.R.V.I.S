import DincrCore
import DincrDesign
import SwiftUI

/// JARVIS agenda (recovery roadmap J2): the Owner's upcoming events for the next 45 days, the
/// historical "Próximos eventos" of JARVIS, as a native list grouped by day. Events are created
/// through the chat, as they always were: "Agendar con JARVIS" opens it; nothing here edits data.
/// Android: `JarvisAgendaScreen`.
struct JarvisAgendaView: View {
    @Environment(AppModel.self) private var model

    var body: some View {
        ScreenScroll(title: tx("Agenda", "Calendar")) {
            // Reloads every time the screen appears: an event confirmed in the chat shows on return.
            AsyncContent(load: { try await model.service.jarvisUpcomingEvents() }) { events, reload in
                if events.isEmpty {
                    EmptyStateView(symbol: "calendar", title: tx("No hay compromisos próximos", "No upcoming commitments"),
                                   message: tx("Pedile a JARVIS que agende algo, por ejemplo “Agendá dentista el 10 de octubre a las 3pm”.",
                                               "Ask JARVIS to schedule something, for example “Agendá dentista el 10 de octubre a las 3pm”.")) {
                        scheduleButton
                    }
                    .accessibilityIdentifier("jarvis.agenda.empty")
                } else {
                    scheduleButton
                    Text(tx("Próximos \(JarvisAgenda.days) días", "Next \(JarvisAgenda.days) days"))
                        .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                    ForEach(JarvisAgenda.days(events)) { day in
                        DayCard(day: day)
                    }
                }
            }
        }
    }

    private var scheduleButton: some View {
        NavigationLink(value: ProfileRoute.jarvisSection(.chat)) {
            Label(tx("Agendar con JARVIS", "Schedule with JARVIS"), systemImage: "bubble.left.and.text.bubble.right")
        }
        .buttonStyle(.dincrPrimary)
        .accessibilityIdentifier("jarvis.agenda.schedule")
    }
}

/// One day: its date, then each event with its time when it has one.
private struct DayCard: View {
    let day: JarvisAgenda.Day

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s3) {
            Text(Self.label(day)).font(DincrFont.title2).foregroundStyle(DincrColor.text)
                .accessibilityAddTraits(.isHeader)
            ForEach(day.events) { event in
                HStack(alignment: .firstTextBaseline, spacing: DincrSpacing.s3) {
                    Text(event.time ?? "—")
                        .font(DincrFont.bodySmall.monospacedDigit().weight(.semibold))
                        .foregroundStyle(event.time == nil ? DincrColor.textMuted : DincrColor.tint)
                        .frame(minWidth: 48, alignment: .leading)
                        .accessibilityHidden(event.time == nil)
                    Text(event.title).font(DincrFont.body).foregroundStyle(DincrColor.text)
                    Spacer(minLength: 0)
                }
                .accessibilityElement(children: .combine)
                .accessibilityIdentifier("jarvis.agenda.event")
            }
        }
        .dincrCard()
    }

    /// "Hoy", "Mañana" or the full date in the session language; the stored text if it is not a date.
    static func label(_ day: JarvisAgenda.Day) -> String {
        guard let date = day.events.first?.date else { return day.day }
        let calendar = Calendar.current
        if calendar.isDateInToday(date) { return tx("Hoy", "Today") }
        if calendar.isDateInTomorrow(date) { return tx("Mañana", "Tomorrow") }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: AppLanguage.current == .spanish ? "es_CR" : "en_US")
        formatter.setLocalizedDateFormatFromTemplate("EEEEdMMMM")
        return formatter.string(from: date).capitalizedFirst
    }
}

private extension String {
    var capitalizedFirst: String { prefix(1).uppercased() + dropFirst() }
}
