import DincrCore
import DincrDesign
import SwiftUI

/// Hoy (UX-6). The public plans get four blocks — Estado de hoy, Para atender, Qué sigue, Accesos
/// rápidos — from `HomeToday`; the plan decides what each block knows (Free facts, Basic + budget
/// and commitments, VIP + safe to spend and the director). The Owner (server role, never a plan) has
/// its own Hoy: JARVIS first, then the same blocks. Read-only: opening Hoy never writes.
struct HomeView: View {
    @Environment(AppModel.self) private var model
    let openMovements: () -> Void

    var body: some View {
        if Jarvis.isAvailable(to: model.profile) {
            OwnerHomeView(openMovements: openMovements)
        } else {
            PublicHomeView(openMovements: openMovements)
        }
    }
}

private struct PublicHomeView: View {
    @Environment(AppModel.self) private var model
    let openMovements: () -> Void
    @State private var state: LoadState<HomeToday> = .loading

    var body: some View {
        let tier = HomeTodayLoader.tier(model)
        ScrollView {
            VStack(alignment: .leading, spacing: DincrSpacing.s4) {
                switch state {
                case .loading:
                    SkeletonView(rows: 3)
                case .failed(let message):
                    ErrorStateView(message: message) { Task { await load(tier) } }
                case .loaded(let home):
                    HomeBlocks(home: home, openMovements: openMovements) { await load(tier) }
                }
            }
            .padding(.horizontal, DincrSpacing.s4)
            .padding(.bottom, DincrSpacing.s6)
            .frame(maxWidth: 640)
            .frame(maxWidth: .infinity)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("home.today")
        }
        .dincrScreenBackground()
        .navigationTitle(tx("Hola, \(model.profile?.firstName ?? "")", "Hi, \(model.profile?.firstName ?? "")"))
        .refreshable { await load(tier) }
        .task(id: tier) { await load(tier) }
    }

    private func load(_ tier: HomeToday.Tier) async {
        let epoch = model.currentEpoch
        do {
            let home = try await HomeTodayLoader.load(model, tier: tier)
            if epoch == model.currentEpoch { state = .loaded(home) }
        } catch is CancellationError {
            return
        } catch {
            if let message = model.message(for: error, epoch: epoch, fallback: tx("No pudimos cargar tu resumen.", "We couldn’t load your overview.")) {
                state = .failed(message)
            }
        }
    }
}

/// Reads what Hoy needs for a plan. The plan's main source is required (its failure is the screen's
/// error); the extras (debts, budget, calendar, strategy) are optional and simply left out when they
/// can't be read. GETs only.
enum HomeTodayLoader {
    /// VIP intelligence is VIP while `vip_intelligence` is on; otherwise VIP reads as Basic (as before).
    @MainActor
    static func tier(_ model: AppModel) -> HomeToday.Tier {
        switch model.planTier {
        case .vip where model.flags.isEnabled(.vipIntelligence): .vip
        case .basic, .vip: .basic
        case .free: .free
        }
    }

    @MainActor
    static func load(_ model: AppModel, tier: HomeToday.Tier) async throws -> HomeToday {
        let service = model.service
        async let debts = optional { try await service.debts() }
        switch tier {
        case .free:
            let dashboard = try await service.freeDashboard()
            return .free(dashboard, debts: await debts)
        case .basic:
            async let budget = optional { try await service.budget() }
            async let calendar = optional { try await service.calendar(period: month()) }
            async let strategy = optional { try await service.strategyBasic() }
            let dashboard = try await service.basicDashboard()
            return .basic(dashboard, budget: await budget, calendar: await calendar,
                          plan: await strategy.map { MonthPlan(.basic($0)) }, debts: await debts)
        case .vip:
            async let budget = optional { try await service.budget() }
            async let calendar = optional { try await service.calendar(period: month()) }
            let center = try await service.commandCenter()
            return .vip(center, budget: await budget, calendar: await calendar, debts: await debts,
                        mailReviewAvailable: model.flags.isEnabled(.gmailAutomation))
        }
    }

    private static func optional<T: Sendable>(_ read: @Sendable () async throws -> T) async -> T? {
        try? await read()
    }

    private static func month() -> String { String(HomeToday.dayKey(.now).prefix(7)) }
}

enum LoadState<Value: Equatable>: Equatable {
    case loading
    case failed(String)
    case loaded(Value)
}
