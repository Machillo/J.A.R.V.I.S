import DincrCore
import DincrDesign
import SwiftUI

/// The Owner's "Hoy" (DINCR Owner redesign). It stays DINCR's Today tab and answers, in order:
/// 1. who and when (greeting with the profile's first name),
/// 2. how am I (the backend's key figure: safe to spend, or the month's balance without VIP intelligence),
/// 3. what needs attention ("Para atender": alerts and mail notices, UX-5),
/// 4. your finances (debts and goals: the same screens the other plans reach from their Today),
/// 5. what comes next (the JARVIS agenda),
/// 6. JARVIS (chat and agenda), also reachable from the mark in the header.
/// Read-only: opening it never writes. Each part loads on its own, so a failing agenda never hides
/// the money, and nothing is invented when the backend sends no value ("—").
struct OwnerHomeView: View {
    @Environment(AppModel.self) private var model
    @State private var summary: LoadState<OwnerSummary> = .loading
    @State private var agenda: LoadState<[JarvisEvent]> = .loading

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DincrSpacing.s4) {
                header
                summarySection
                attentionSection
                financesSection
                upcomingSection
                jarvisSection
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
            await loadSummary()
            await loadAgenda()
        }
        // Two independent tasks: the money and the agenda load in parallel and fail separately.
        .task { await loadSummary() }
        .task { await loadAgenda() }
    }

    // MARK: 1. Greeting

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

    // MARK: 2. Money

    @ViewBuilder
    private var summarySection: some View {
        switch summary {
        case .loading:
            SkeletonView(rows: 1)
        case .failed(let message):
            ErrorStateView(message: message) { Task { await loadSummary() } }
        case .loaded(.center(let center)):
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                Text(tx("Podés gastar con tranquilidad", "Safe to spend")).font(DincrFont.label).foregroundStyle(OwnerColor.text2)
                MoneyText(center.safeToSpend?.amount, font: DincrFont.displayAmount)
                    .accessibilityIdentifier("owner.home.hero")
                FigureRow(label: tx("Margen del mes", "Monthly margin"), amount: center.safeToSpend?.monthlyMargin)
                FigureRow(label: tx("Saldo mínimo previsto (45 días)", "Lowest expected balance (45 days)"),
                          amount: center.safeToSpend?.next45DaysMinimum)
                if let headline = center.director?.headline, !headline.isEmpty {
                    OwnerDivider().padding(.vertical, DincrSpacing.s1)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(tx("Tu prioridad", "Your priority")).font(DincrFont.caption).foregroundStyle(OwnerColor.textMuted)
                        Text(headline).font(DincrFont.body.weight(.semibold)).foregroundStyle(OwnerColor.text)
                        if let next = center.director?.nextAction, !next.isEmpty {
                            Text(next).font(DincrFont.bodySmall).foregroundStyle(OwnerColor.text2)
                        }
                    }
                    .accessibilityElement(children: .combine)
                }
            }
            .dincrCard()
        case .loaded(.basic(let dashboard)):
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                Text(tx("Balance del mes", "Balance this month")).font(DincrFont.label).foregroundStyle(OwnerColor.text2)
                MoneyText(dashboard.balance, font: DincrFont.displayAmount)
                    .accessibilityIdentifier("owner.home.hero")
                FigureRow(label: tx("Ingresos", "Income"), amount: dashboard.income, sign: .income)
                FigureRow(label: tx("Gastos", "Expenses"), amount: dashboard.expenses, sign: .expense)
            }
            .dincrCard()
        }
    }

    // MARK: 3. Attention

    /// UX-5: the same "Para atender" as VIP (critical → high → medium → success). Only from a loaded
    /// command center: with VIP intelligence off, or nothing to show, the section is left out — never
    /// a "Nada pendiente" DINCR hasn't checked.
    @ViewBuilder
    private var attentionSection: some View {
        if case .loaded(let value) = summary, let center = value.center {
            AttentionSection(today: AttentionList.today(center: center, mailReviewAvailable: model.flags.isEnabled(.gmailAutomation)),
                             idPrefix: "owner.home.attention", ownerStyle: true)
        }
    }

    // MARK: 4. Finances

    /// Debts and goals left the Plan tab for Today; the Owner's Today keeps them, opening the same
    /// screens (navigation only: their data and rules are unchanged).
    @ViewBuilder
    private var financesSection: some View {
        OwnerSectionHeader(tx("Tus finanzas", "Your finances"))
        OwnerGroup {
            NavigationLink { DebtsView() } label: {
                OwnerRow(symbol: "creditcard", title: tx("Deudas", "Debts"),
                         detail: tx("Saldos, pagos y avance", "Balances, payments and progress"))
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("owner.home.debts")
            OwnerDivider()
            NavigationLink { GoalsView() } label: {
                OwnerRow(symbol: "target", title: tx("Metas y ahorro", "Goals and savings"),
                         detail: tx("Metas, aportes y planes de ahorro", "Goals, contributions and savings plans"))
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("owner.home.goals")
        }
    }

    // MARK: 5. Next

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

    // MARK: 6. JARVIS

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

    private func loadSummary() async {
        let epoch = model.currentEpoch
        do {
            let value: OwnerSummary = model.flags.isEnabled(.vipIntelligence)
                ? .center(try await model.service.commandCenter())
                : .basic(try await model.service.basicDashboard())
            if epoch == model.currentEpoch { summary = .loaded(value) }
        } catch is CancellationError {
            return
        } catch {
            if let message = model.message(for: error, epoch: epoch, fallback: tx("No pudimos cargar tu resumen.", "We couldn’t load your overview.")) {
                summary = .failed(message)
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

/// The Owner's money summary: the VIP command center, or the month's dashboard while VIP intelligence is off.
enum OwnerSummary: Equatable {
    case center(CommandCenter)
    case basic(BasicDashboard)

    var center: CommandCenter? {
        if case .center(let value) = self { return value }
        return nil
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
