import DincrCore
import DincrDesign
import SwiftUI

/// "Para atender" on Hoy (UX-5): the first items of `AttentionList.today` and "Ver todas" when there
/// are more. With nothing to show the section is left out entirely (never an empty or "all clear"
/// block). VIP and the Owner share it; `idPrefix` keeps each Hoy's identifiers.
struct AttentionSection: View {
    let today: AttentionList.Today
    var idPrefix = "home.attention"
    var ownerStyle = false

    var body: some View {
        if !today.isEmpty {
            VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                if ownerStyle {
                    OwnerSectionHeader(tx("Para atender", "Needs attention")) { seeAll }
                } else {
                    HStack(alignment: .firstTextBaseline) {
                        SectionHeader(title: tx("Para atender", "Needs attention"))
                        Spacer(minLength: DincrSpacing.s2)
                        seeAll.font(DincrFont.bodySmall.weight(.semibold))
                    }
                }
                ForEach(today.visible) { item in
                    AttentionRow(item: item, idPrefix: idPrefix)
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(idPrefix)
        }
    }

    @ViewBuilder
    private var seeAll: some View {
        if today.showsSeeAll {
            NavigationLink(tx("Ver todas", "See all")) { AttentionListView() }
                .frame(minHeight: 44)
                .accessibilityIdentifier("\(idPrefix).all")
        }
    }
}

/// One item: the message in its UX-1 meaning, "change since the last observation" for the advisor's
/// items, and a link only when the item has a real destination.
struct AttentionRow: View {
    let item: AttentionItem
    var idPrefix = "attention"

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s1) {
            DincrMessage(item.kind, title: item.title, message: item.message)
            if item.isChange {
                Text(tx("Cambio desde la última observación", "Change since the last check"))
                    .font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                    .padding(.horizontal, DincrSpacing.s4)
            }
            if let destination = item.destination {
                NavigationLink { AttentionDestinationView(destination: destination) } label: {
                    HStack(spacing: DincrSpacing.s1) {
                        Text(destination.title)
                        Image(systemName: "chevron.right").font(DincrFont.caption).accessibilityHidden(true)
                    }
                    .font(DincrFont.bodySmall.weight(.semibold))
                    .foregroundStyle(DincrColor.tint)
                    .frame(minHeight: 44)
                    .padding(.horizontal, DincrSpacing.s4)
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("\(idPrefix).link.\(destination.rawValue)")
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("\(idPrefix).item.\(item.source.name)")
    }
}

/// "Ver todas": every item, uncapped, with the proactive advisor's changes (D-3). Read-only: both
/// sources are GETs. If the advisor can't be read, the command center's items still show and the
/// failure is said as a technical problem, never as "nothing pending".
struct AttentionListView: View {
    @Environment(AppModel.self) private var model
    @State private var center: LoadState<CommandCenter> = .loading
    @State private var advisor: LoadState<ProactiveAdvisor> = .loading
    /// The advisor can't be read for this account right now (paused or not in its plan): its
    /// changes are simply not shown, without a technical message and without claiming "nothing".
    @State private var advisorUnavailable = false

    var body: some View {
        ScreenScroll(title: tx("Para atender", "Needs attention")) {
            switch center {
            case .loading:
                SkeletonView(rows: 3)
            case .failed(let message):
                ErrorStateView(message: message) { Task { await load() } }
            case .loaded(let value):
                let items = AttentionList.items(center: value, advisor: advisor.value,
                                                mailReviewAvailable: model.flags.isEnabled(.gmailAutomation))
                ForEach(items) { item in
                    AttentionRow(item: item, idPrefix: "attention")
                }
                switch advisor {
                case .loading:
                    SkeletonView(rows: 1, showsFigure: false)
                case .failed where advisorUnavailable:
                    EmptyView()
                case .failed:
                    DincrMessage(.technicalError, title: tx("No pudimos revisar los cambios recientes", "We couldn’t check recent changes"),
                                 message: tx("Lo de arriba sigue vigente. Probá de nuevo en un momento.", "What’s above still applies. Try again in a moment."))
                        .accessibilityIdentifier("attention.advisor.unavailable")
                case .loaded:
                    // Both sources answered: only now is "nothing" a fact.
                    if items.isEmpty {
                        Text(tx("No hay nada para atender en este momento.", "There’s nothing that needs attention right now."))
                            .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                            .accessibilityIdentifier("attention.none")
                    }
                }
            }
        }
        .accessibilityIdentifier("attention.list")
        .refreshable { await load() }
        .task { await load() }
    }

    private func load() async {
        let epoch = model.currentEpoch
        async let centerResult = result { try await model.service.commandCenter() }
        async let advisorResult = result { try await model.service.proactiveAdvisor() }
        let (loadedCenter, loadedAdvisor) = await (centerResult, advisorResult)
        guard epoch == model.currentEpoch else { return }
        switch loadedCenter {
        case .success(let value): center = .loaded(value)
        case .failure(is CancellationError): return
        case .failure(let error):
            if let message = model.message(for: error, epoch: epoch, fallback: tx("No pudimos cargar lo que necesita tu atención.", "We couldn’t load what needs your attention.")) {
                center = .failed(message)
            }
        }
        switch loadedAdvisor {
        case .success(let value): advisorUnavailable = false; advisor = .loaded(value)
        case .failure(is CancellationError): return
        case .failure(let error):
            advisorUnavailable = AttentionList.isUnavailable(error)
            advisor = .failed("")
        }
    }

    private func result<T>(_ load: () async throws -> T) async -> Result<T, Error> {
        do { return .success(try await load()) } catch { return .failure(error) }
    }
}

/// The screens an item opens: the same ones the rest of the app reaches (navigation only).
struct AttentionDestinationView: View {
    let destination: AttentionItem.Destination

    var body: some View {
        switch destination {
        case .review: EmailMonitorView()
        case .debts: DebtsView()
        case .salvavidas: SalvavidasView()
        case .incomeBase: IncomeBaseView()
        case .strategy: PlanStrategyView()
        case .movements: MovementsView()
        case .monthlyReview: MonthlyReviewView()
        }
    }
}

extension AttentionItem.Destination {
    var title: String {
        switch self {
        case .review: tx("Revisar avisos del correo", "Review mail notices")
        case .debts: tx("Ver deudas", "See debts")
        case .salvavidas: tx("Ver Salvavidas", "See Salvavidas")
        case .incomeBase: tx("Ver ingresos y base", "See income and base")
        case .strategy: tx("Ver tu plan del mes", "See your plan for the month")
        case .movements: tx("Ver movimientos", "See transactions")
        case .monthlyReview: tx("Ver revisión del mes", "See monthly review")
        }
    }
}

private extension LoadState {
    var value: Value? {
        if case .loaded(let value) = self { return value }
        return nil
    }
}

extension AttentionItem.Source {
    var name: String {
        switch self {
        case .commandCenter: "center"
        case .advisor: "advisor"
        case .review: "review"
        }
    }
}
