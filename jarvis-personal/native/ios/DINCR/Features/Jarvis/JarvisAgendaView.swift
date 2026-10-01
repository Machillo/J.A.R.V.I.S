import DincrCore
import DincrDesign
import SwiftUI

/// JARVIS agenda (recovery roadmap J2): the Owner's upcoming events for the next 45 days, the
/// historical "Próximos eventos" of JARVIS, as a native grouped list: one section per day, the next
/// event first. Events are created through the chat, as they always were: "Agendar con JARVIS" opens
/// it; nothing here edits data. Android: `JarvisAgendaScreen`.
struct JarvisAgendaView: View {
    @Environment(AppModel.self) private var model
    @State private var state: LoadState<[JarvisEvent]> = .loading

    var body: some View {
        Group {
            switch state {
            case .loading:
                ScrollView { SkeletonView(rows: 3, showsFigure: false).padding(DincrSpacing.s4) }
            case .failed(let message):
                ScrollView {
                    ErrorStateView(message: message) { Task { await load() } }.padding(DincrSpacing.s4)
                }
            case .loaded(let events) where events.isEmpty:
                ScrollView { empty.padding(DincrSpacing.s4) }
            case .loaded(let events):
                list(JarvisAgenda.days(events))
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .dincrScreenBackground()
        .navigationTitle(tx("Agenda", "Calendar"))
        .toolbar {
            if hasEvents {
                ToolbarItem(placement: .topBarTrailing) { scheduleLink(prominent: false) }
            }
        }
        .refreshable { await load() }
        // Runs every time the screen appears: an event confirmed in the chat shows on return. The
        // list already shown stays while it reloads.
        .task { await load() }
    }

    private var hasEvents: Bool {
        if case .loaded(let events) = state { return !events.isEmpty }
        return false
    }

    private var empty: some View {
        EmptyStateView(symbol: "calendar", title: tx("No hay compromisos próximos", "No upcoming commitments"),
                       message: tx("Pedile a JARVIS que agende algo, por ejemplo “Agendá dentista el 10 de octubre a las 3pm”.",
                                   "Ask JARVIS to schedule something, for example “Agendá dentista el 10 de octubre a las 3pm”.")) {
            scheduleLink(prominent: true)
        }
        // A container element, so its identifier does not replace the button's.
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("jarvis.agenda.empty")
    }

    private func list(_ days: [JarvisAgenda.Day]) -> some View {
        List {
            Section {
                Text(tx("Próximos \(JarvisAgenda.days) días", "Next \(JarvisAgenda.days) days"))
                    .font(DincrFont.bodySmall).foregroundStyle(OwnerColor.text2)
                    .listRowBackground(Color.clear)
                    .listRowInsets(EdgeInsets(top: 0, leading: DincrSpacing.s4, bottom: 0, trailing: DincrSpacing.s4))
            }
            ForEach(days) { day in
                Section {
                    ForEach(day.events) { event in EventRow(event: event) }
                } header: {
                    Text(Self.label(day)).font(DincrFont.title2).foregroundStyle(OwnerColor.text).textCase(nil)
                        .accessibilityAddTraits(.isHeader)
                }
                .dincrRowBackground()
            }
        }
        .listStyle(.insetGrouped)
        .dincrListBackground()
    }

    @ViewBuilder
    private func scheduleLink(prominent: Bool) -> some View {
        let link = NavigationLink(value: ProfileRoute.jarvisSection(.chat)) {
            Label(tx("Agendar con JARVIS", "Schedule with JARVIS"), systemImage: "calendar.badge.plus")
        }
        if prominent {
            link.buttonStyle(.dincrPrimary).accessibilityIdentifier("jarvis.agenda.schedule")
        } else {
            link.accessibilityIdentifier("jarvis.agenda.schedule")
        }
    }

    /// "Hoy", "Mañana" or the full date in the session language; the stored text if it is not a date.
    static func label(_ day: JarvisAgenda.Day) -> String {
        guard let date = day.events.first?.date else { return day.day }
        return JarvisAgendaLabel.day(date, fallback: day.day)
    }

    private func load() async {
        let epoch = model.currentEpoch
        do {
            let events = try await model.service.jarvisUpcomingEvents()
            if epoch == model.currentEpoch { state = .loaded(events) }
        } catch is CancellationError {
            return
        } catch {
            if let message = model.message(for: error, epoch: epoch, fallback: tx("No pudimos cargar tu agenda.", "We couldn’t load your calendar.")) {
                // A reload that fails keeps the list already shown; only a first load shows the error.
                if case .loaded = state { return }
                state = .failed(message)
            }
        }
    }
}

/// One event: its time (or "Todo el día") and its title.
private struct EventRow: View {
    let event: JarvisEvent

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: DincrSpacing.s3) {
            Text(event.time ?? tx("Todo el día", "All day"))
                .font(DincrFont.bodySmall.monospacedDigit().weight(.semibold))
                .foregroundStyle(event.time == nil ? OwnerColor.text2 : OwnerColor.accent)
                .frame(minWidth: 56, alignment: .leading)
            Text(event.title).font(DincrFont.body).foregroundStyle(OwnerColor.text)
            Spacer(minLength: 0)
        }
        .padding(.vertical, DincrSpacing.s1)
        .frame(minHeight: 44)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("jarvis.agenda.event")
    }
}
