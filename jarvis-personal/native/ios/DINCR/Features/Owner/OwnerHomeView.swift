import DincrCore
import DincrDesign
import SwiftUI

/// The Owner's "Hoy" (DINCR Owner; UX-6). The Owner is Kenneth's identity, not a plan: JARVIS comes
/// first, as it historically did, and the financial blocks follow.
/// 0. JARVIS — who and when (greeting), the one entry to JARVIS and the next agenda events;
/// 1–4. the same four blocks as the public Hoy (Estado de hoy, Para atender, Qué sigue, Accesos
///    rápidos), from the command center while `vip_intelligence` is on (Basic's sources otherwise).
/// Read-only: opening it never writes. The money and the agenda load on their own, so a failing
/// agenda never hides the money, and nothing is invented when the backend sends no value ("—").
struct OwnerHomeView: View {
    @Environment(AppModel.self) private var model
    var openMovements: (() -> Void)?
    @State private var home: LoadState<HomeToday> = .loading
    @State private var agenda: LoadState<[JarvisEvent]> = .loading
    @State private var unreadNotices = 0

    var body: some View {
        let tier = ownerTier
        ScrollView {
            VStack(alignment: .leading, spacing: DincrSpacing.s4) {
                header
                jarvisSection
                upcomingSection
                PendingDollarsCard(openMovements: openMovements)
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
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                NavigationLink { OwnerNoticesView() } label: {
                    Image(systemName: unreadNotices > 0 ? "bell.badge" : "bell")
                }
                .accessibilityLabel(unreadNotices > 0 ? tx("Avisos, \(unreadNotices) sin leer", "Notices, \(unreadNotices) unread") : tx("Avisos", "Notices"))
                .accessibilityIdentifier("owner.home.notices")
            }
        }
        .refreshable {
            await loadHome(tier)
            await loadAgenda()
            await loadNotices()
        }
        .onAppear { Task { await loadNotices() } }
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
                    if index > 0 { OwnerDivider(inset: 0) }
                    OwnerAgendaRow(event: event)
                }
            }
        }
    }

    // MARK: 0. JARVIS — the one way in

    private var jarvisSection: some View {
        OwnerGroup {
            NavigationLink(value: ProfileRoute.jarvis) {
                OwnerRow(symbol: "sparkles", title: "JARVIS",
                         detail: tx("Chat, agenda, estrategia, mi dinero y todo lo demás", "Chat, calendar, strategy, my money and everything else"))
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("owner.home.jarvis")
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

    /// Only the bell's count: a failure leaves it as it was, never hiding the rest of Hoy.
    private func loadNotices() async {
        if let notices = try? await model.service.ownerNotices() { unreadNotices = notices.unread ?? 0 }
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

/// One agenda event: its title, and its day ("Hoy", "Mañana" or the date) with the time when it has one.
struct OwnerAgendaRow: View {
    let event: JarvisEvent

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(event.title).font(DincrFont.body).foregroundStyle(OwnerColor.text)
            Text("\(JarvisAgendaLabel.day(event)) · \(event.time ?? tx("Todo el día", "All day"))")
                .font(DincrFont.bodySmall).foregroundStyle(OwnerColor.text2)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
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
