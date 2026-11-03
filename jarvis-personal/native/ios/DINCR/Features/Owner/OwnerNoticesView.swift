import DincrCore
import DincrDesign
import SwiftUI

/// The Owner's notices (Hoy → the bell): what changed in his money, newest first. Opening one marks it
/// read and shows what it means today. Every sentence comes from the backend (`ai/owner_notices.py`).
struct OwnerNoticesView: View {
    @Environment(AppModel.self) private var model
    @State private var state: LoadState<OwnerNotices> = .loading

    var body: some View {
        List {
            switch state {
            case .loading:
                Section { SkeletonView(rows: 3, showsFigure: false).listRowInsets(EdgeInsets()) }.listRowBackground(Color.clear)
            case .failed(let message):
                Section { ErrorStateView(message: message) { Task { await load() } } }.listRowBackground(Color.clear).listRowInsets(EdgeInsets())
            case .loaded(let notices):
                if notices.items.isEmpty {
                    Section {
                        EmptyStateView(symbol: "bell", title: tx("Sin avisos", "No notices"),
                                       message: tx("Cuando algo cambie en tu plata, te lo contamos aquí.", "When something changes in your money, we'll tell you here.")) { EmptyView() }
                    }
                    .listRowBackground(Color.clear).listRowInsets(EdgeInsets())
                }
                Section {
                    ForEach(notices.items) { notice in
                        NavigationLink {
                            OwnerNoticeDetailView(notice: notice)
                        } label: {
                            HStack(alignment: .firstTextBaseline, spacing: DincrSpacing.s2) {
                                Circle().fill(notice.read == true ? AnyShapeStyle(.clear) : AnyShapeStyle(.dincrTint)).frame(width: 8, height: 8)
                                    .accessibilityLabel(notice.read == true ? "" : tx("Sin leer", "Unread"))
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(notice.title ?? tx("Aviso", "Notice")).font(DincrFont.body).foregroundStyle(.dincrText)
                                    if let changed = notice.changed { Text(changed).font(DincrFont.bodySmall).foregroundStyle(.dincrText2) }
                                }
                            }
                        }
                        .accessibilityIdentifier("owner.notices.\(notice.id)")
                    }
                }
                .dincrRowBackground()
            }
        }
        .listStyle(.insetGrouped)
        .dincrListBackground()
        .navigationTitle(tx("Avisos", "Notices"))
        .navigationBarTitleDisplayMode(.inline)
        .refreshable { await load() }
        .task { await load() }
        .onAppear { Task { await load() } }
        .accessibilityIdentifier("owner.notices")
    }

    private func load() async {
        let epoch = model.currentEpoch
        do {
            let value = try await model.service.ownerNotices()
            if epoch == model.currentEpoch { state = .loaded(value) }
        } catch is CancellationError {
            return
        } catch {
            if case .loaded = state { return }
            if let message = model.message(for: error, epoch: epoch, fallback: tx("No pudimos cargar tus avisos.", "We couldn’t load your notices.")) {
                state = .failed(message)
            }
        }
    }
}

/// One notice: what changed, where the money goes, what the automatic savings do, and when the debts end.
struct OwnerNoticeDetailView: View {
    @Environment(AppModel.self) private var model
    let notice: OwnerNotices.Notice

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DincrSpacing.s4) {
                Text(notice.title ?? tx("Aviso", "Notice")).font(.title2.weight(.bold)).foregroundStyle(.dincrText)
                    .accessibilityAddTraits(.isHeader)
                OwnerGroup {
                    section(tx("Qué cambió", "What changed"), notice.changed, id: "changed")
                    if let destination = notice.destination {
                        OwnerDivider(inset: 0)
                        section(tx("A dónde se va", "Where it goes"), destination, id: "destination")
                    }
                    if let savings = notice.savings?.text {
                        OwnerDivider(inset: 0)
                        section(tx("Ahorro automático", "Automatic savings"), savings, id: "savings")
                    }
                    if let day = monthLabel(notice.debtFreeDate) {
                        OwnerDivider(inset: 0)
                        section(tx("Salís de deudas", "Debt-free"), tx("\(day) (estimado)", "\(day) (estimated)"), id: "debtFree")
                    }
                }
                NavigationLink(tx("Ver mi plan", "See my plan")) { PlanStrategyView() }
                    .buttonStyle(.dincrSecondary)
                    .accessibilityIdentifier("owner.notice.plan")
            }
            .padding(DincrSpacing.s4)
            .frame(maxWidth: 640)
            .frame(maxWidth: .infinity)
        }
        .dincrScreenBackground()
        .navigationBarTitleDisplayMode(.inline)
        .accessibilityIdentifier("owner.notice")
        // Reading it is the Owner's own action; a failure only leaves it unread.
        .task { if notice.read != true { try? await model.service.markOwnerNoticeRead(id: notice.id) } }
    }

    private func section(_ label: String, _ text: String?, id: String) -> some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s1) {
            Text(label).font(DincrFont.caption).foregroundStyle(.dincrText2)
            Text(text ?? "—").font(DincrFont.body).foregroundStyle(.dincrText)
        }
        .padding(.vertical, DincrSpacing.s3)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("owner.notice.\(id)")
    }

    private func monthLabel(_ day: String?) -> String? {
        guard let day else { return nil }
        let parser = DateFormatter()
        parser.calendar = Calendar(identifier: .gregorian)
        parser.locale = Locale(identifier: "en_US_POSIX")
        parser.dateFormat = "yyyy-MM-dd"
        guard let date = parser.date(from: String(day.prefix(10))) else { return nil }
        let output = DateFormatter()
        output.locale = Locale(identifier: AppLanguage.current == .spanish ? "es_CR" : "en_US")
        output.setLocalizedDateFormatFromTemplate("MMMMyyyy")
        return output.string(from: date)
    }
}
