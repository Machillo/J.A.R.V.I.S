import DincrCore
import DincrDesign
import SwiftUI

/// The Owner's "Hoy" (DINCR Owner; UX-6). The Owner is Kenneth's identity, not a plan: JARVIS comes
/// first, as it historically did, and the financial blocks follow.
/// 0. JARVIS — who and when (greeting), the JARVIS mark, Chat / Agenda / Todo JARVIS and the next
///    agenda events;
/// 1–4. the same four blocks as the public Hoy (Estado de hoy, Para atender, Qué sigue, Accesos
///    rápidos), from the command center while `vip_intelligence` is on (Basic's sources otherwise).
/// Read-only: opening it never writes. The money and the agenda load on their own, so a failing
/// agenda never hides the money, and nothing is invented when the backend sends no value ("—").
struct OwnerHomeView: View {
    @Environment(AppModel.self) private var model
    var openMovements: (() -> Void)?
    @State private var home: LoadState<HomeToday> = .loading
    @State private var agenda: LoadState<[JarvisEvent]> = .loading

    var body: some View {
        let tier = ownerTier
        ScrollView {
            VStack(alignment: .leading, spacing: DincrSpacing.s4) {
                header
                jarvisSection
                upcomingSection
                financesSection(tier)
            }
            .padding(.horizontal, DincrSpacing.s4)
            .padding(.bottom, DincrSpacing.s8)
            .frame(maxWidth: 640)
            .frame(maxWidth: .infinity)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("owner.home")
        }
        .dincrScreenBackground()
        .navigationTitle(tx("Hoy", "Today"))
        .navigationBarTitleDisplayMode(.inline)
        .refreshable {
            await loadHome(tier)
            await loadAgenda()
        }
        // Two independent tasks: the money and the agenda load in parallel and fail separately.
        .task(id: tier) { await loadHome(tier) }
        .task { await loadAgenda() }
    }

    /// The Owner's financial blocks read the command center while VIP intelligence is on (as before).
    private var ownerTier: HomeToday.Tier { model.flags.isEnabled(.vipIntelligence) ? .vip : .basic }

    // MARK: 0. JARVIS — greeting

    private var header: some View {
        HStack(alignment: .center, spacing: DincrSpacing.s3) {
            VStack(alignment: .leading, spacing: 2) {
                Text(greeting).font(DincrFont.title2.weight(.regular)).foregroundStyle(OwnerColor.text2)
                if let name = model.profile?.firstName, !name.isEmpty {
                    Text("\(name).").font(.largeTitle.weight(.bold)).foregroundStyle(OwnerColor.text)
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityAddTraits(.isHeader)
            .accessibilityIdentifier("owner.home.greeting")
            Spacer(minLength: DincrSpacing.s2)
            NavigationLink(value: ProfileRoute.jarvisSection(.chat)) {
                JarvisMark(size: 52)
            }
            .buttonStyle(.plain)
            .frame(minWidth: 44, minHeight: 44)
            .accessibilityLabel(tx("Abrir JARVIS", "Open JARVIS"))
            .accessibilityIdentifier("owner.home.jarvis.mark")
        }
        .padding(.top, DincrSpacing.s2)
    }

    private var greeting: String {
        switch OwnerHome.greeting(at: .now) {
        case .morning: tx("Buenos días,", "Good morning,")
        case .afternoon: tx("Buenas tardes,", "Good afternoon,")
        case .evening: tx("Buenas noches,", "Good evening,")
        }
    }

    // MARK: 1–4. Finances

    @ViewBuilder
    private func financesSection(_ tier: HomeToday.Tier) -> some View {
        switch home {
        case .loading:
            SkeletonView(rows: 2)
        case .failed(let message):
            ErrorStateView(message: message) { Task { await loadHome(tier) } }
        case .loaded(let value):
            HomeBlocks(home: value, idPrefix: "owner.home", ownerStyle: true, openMovements: openMovements) { await loadHome(tier) }
        }
    }

    // MARK: 0. JARVIS — agenda

    @ViewBuilder
    private var upcomingSection: some View {
        OwnerSectionHeader(tx("Próximos", "Coming up")) {
            NavigationLink(tx("Ver agenda", "See calendar"), value: ProfileRoute.jarvisSection(.calendar))
                .frame(minHeight: 44)
                .accessibilityIdentifier("owner.home.agenda.all")
        }
        switch agenda {
        case .loading:
            SkeletonView(rows: 2, showsFigure: false)
        case .failed(let message):
            ErrorStateView(message: message) { Task { await loadAgenda() } }
        case .loaded(let events):
            let next = OwnerHome.upcoming(events)
            OwnerGroup {
                if next.isEmpty {
                    NavigationLink(value: ProfileRoute.jarvisSection(.chat)) {
                        OwnerRow(symbol: "calendar.badge.plus", title: tx("Sin compromisos próximos", "No upcoming commitments"),
                                 detail: tx("Agendá con JARVIS", "Schedule with JARVIS"))
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("owner.home.agenda.empty")
                }
                ForEach(Array(next.enumerated()), id: \.element.id) { index, event in
                    if index > 0 { OwnerDivider() }
                    OwnerAgendaRow(event: event)
                }
            }
        }
    }

    // MARK: 0. JARVIS — chat, agenda, everything

    @ViewBuilder
    private var jarvisSection: some View {
        OwnerSectionHeader("JARVIS")
        OwnerGroup {
            NavigationLink(value: ProfileRoute.jarvisSection(.chat)) {
                OwnerRow(symbol: "bubble.left.and.text.bubble.right", title: tx("Chat", "Chat"),
                         detail: tx("Horas extra, VGH, feriados, bonos y tu agenda", "Overtime, VGH, holidays, bonuses and your calendar"))
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("owner.home.jarvis.chat")
            OwnerDivider()
            NavigationLink(value: ProfileRoute.jarvisSection(.calendar)) {
                OwnerRow(symbol: "calendar", title: tx("Agenda", "Calendar"), detail: tx("Tus eventos y recordatorios", "Your events and reminders"))
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("owner.home.jarvis.agenda")
            OwnerDivider()
            NavigationLink(value: ProfileRoute.jarvis) {
                OwnerRow(symbol: "square.grid.2x2", title: tx("Todo JARVIS", "All of JARVIS"), detail: tx("Tu espacio personal", "Your personal space"))
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("owner.home.jarvis.hub")
        }
    }

    // MARK: Loading

    private func loadHome(_ tier: HomeToday.Tier) async {
        let epoch = model.currentEpoch
        do {
            let value = try await HomeTodayLoader.load(model, tier: tier)
            if epoch == model.currentEpoch { home = .loaded(value) }
        } catch is CancellationError {
            return
        } catch {
            if let message = model.message(for: error, epoch: epoch, fallback: tx("No pudimos cargar tu resumen.", "We couldn’t load your overview.")) {
                home = .failed(message)
            }
        }
    }

    private func loadAgenda() async {
        let epoch = model.currentEpoch
        do {
            let events = try await model.service.jarvisUpcomingEvents()
            if epoch == model.currentEpoch { agenda = .loaded(events) }
        } catch is CancellationError {
            return
        } catch {
            if let message = model.message(for: error, epoch: epoch, fallback: tx("No pudimos cargar tu agenda.", "We couldn’t load your calendar.")) {
                agenda = .failed(message)
            }
        }
    }
}

/// One agenda event: its day ("Hoy", "Mañana" or the date) with the time when it has one, and its title.
struct OwnerAgendaRow: View {
    let event: JarvisEvent

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: DincrSpacing.s3) {
            VStack(alignment: .leading, spacing: 2) {
                Text(JarvisAgendaLabel.day(event)).font(DincrFont.caption).foregroundStyle(OwnerColor.textMuted)
                Text(event.time ?? tx("Todo el día", "All day"))
                    .font(DincrFont.bodySmall.monospacedDigit().weight(.semibold))
                    .foregroundStyle(event.time == nil ? OwnerColor.text2 : OwnerColor.accent)
            }
            .frame(minWidth: 72, alignment: .leading)
            Text(event.title).font(DincrFont.body).foregroundStyle(OwnerColor.text)
            Spacer(minLength: 0)
        }
        .padding(.vertical, DincrSpacing.s3)
        .frame(minHeight: 44)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("owner.home.agenda.event")
    }
}

/// Day labels of the agenda: "Hoy", "Mañana" or the full date in the session language; the stored
/// text when it is not a real day (never reinterpreted).
enum JarvisAgendaLabel {
    static func day(_ event: JarvisEvent) -> String {
        guard let date = event.date else { return event.day }
        return day(date, fallback: event.day)
    }

    static func day(_ date: Date, fallback: String) -> String {
        let calendar = Calendar.current
        if calendar.isDateInToday(date) { return tx("Hoy", "Today") }
        if calendar.isDateInTomorrow(date) { return tx("Mañana", "Tomorrow") }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: AppLanguage.current == .spanish ? "es_CR" : "en_US")
        formatter.setLocalizedDateFormatFromTemplate("EEEEdMMMM")
        let text = formatter.string(from: date)
        return text.prefix(1).uppercased() + text.dropFirst()
    }
}
