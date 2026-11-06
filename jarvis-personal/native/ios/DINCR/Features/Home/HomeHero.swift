import DincrCore
import DincrDesign
import SwiftUI

/// The top of Hoy in every plan: greeting, the day's key figure and the main actions on one solid color
/// (DESIGN.md). Read-only figures: the same `HomeStatus` the blocks below use, and unknown stays "—"
/// (the block below says what DINCR needs). JARVIS appears only when the caller is the Owner's Hoy.
struct HomeHero: View {
    var idPrefix = "home"
    var showsJarvis = false
    /// VIP and the Owner: goals and savings with the hero's buttons, all on one row (OW-2, VIP-1).
    var showsGoals = false
    let greeting: String
    let name: String?
    let status: HomeStatus?
    let cycle: String?
    let register: (Movement.Kind) -> Void
    @Environment(\.moneyFormat) private var format
    @Environment(AppModel.self) private var model
    /// The dollars of this month still waiting for their close, as an estimate; nil: none or unknown.
    @State private var dollars: Decimal?

    var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s4) {
            VStack(alignment: .leading, spacing: 2) {
                Text(greeting).font(DincrFont.body).foregroundStyle(OwnerColor.onHero2)
                if let name, !name.isEmpty {
                    Text("\(name).").font(.title.weight(.bold)).foregroundStyle(OwnerColor.onHero)
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityAddTraits(.isHeader)
            .accessibilityIdentifier("\(idPrefix).greeting")
            if let status { figure(status) }
            if showsJarvis || showsGoals {
                // VIP's and the Owner's entries stay on one row: icon over a one-word title.
                HStack(spacing: DincrSpacing.s2) { actions }
                    .labelStyle(HeroTileLabelStyle())
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(spacing: DincrSpacing.s2) { actions }
                    VStack(spacing: DincrSpacing.s2) { actions }
                }
            }
        }
        .padding(.horizontal, DincrSpacing.s4)
        .padding(.top, DincrSpacing.s2)
        .padding(.bottom, DincrSpacing.s6)
        .frame(maxWidth: 640, alignment: .leading)
        .frame(maxWidth: .infinity)
        .task(id: "\(model.dataGeneration)-\(status?.cycle?.start ?? "")") {
            // Optional: Hoy never fails because of it; on error the figures stay as registered.
            // The Owner's statement already counts its dollars (the server's projected statement).
            if !showsJarvis, let read = try? await model.service.pendingConversion() {
                dollars = status?.cycle.map { read.estimate(from: $0.start, through: $0.end).sum } ?? read.estimate(month: String(Day.today().prefix(7)), query: "").sum
            }
        }
    }

    private func figure(_ status: HomeStatus) -> some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s3) {
            VStack(alignment: .leading, spacing: DincrSpacing.s1) {
                Text(status.headline == .safeToSpend ? tx("Podés gastar con tranquilidad", "Safe to spend") : tx("Resultado del mes", "This month’s result"))
                    .font(DincrFont.label).foregroundStyle(OwnerColor.onHero2)
                amount(status.amount, sign: .none, font: .system(size: 44, weight: .bold, design: .rounded).monospacedDigit())
                    // Unknown is "—", never reported as an amount.
                    .accessibilityIdentifier(status.amount == nil ? "\(idPrefix).status.noFigure" : "\(idPrefix).status.amount")
                if let cycle {
                    Text(cycle).font(DincrFont.caption).foregroundStyle(OwnerColor.onHero2)
                        .accessibilityIdentifier("\(idPrefix).status.cycle")
                }
            }
            // Stacks instead of splitting a word when the text is large.
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: DincrSpacing.s4) { facts(status) }
                VStack(alignment: .leading, spacing: DincrSpacing.s2) { facts(status) }
            }
            .accessibilityIdentifier("\(idPrefix).status.facts")
            // The Owner's three figures add up by themselves; under them, what a negative statement asks for.
            if showsJarvis, let hours = status.otHoursToCover {
                Text(hours == 1 ? tx("Necesitás 1 hora de OT para cubrir el saldo negativo.", "You need 1 hour of OT to cover the negative balance.")
                                : tx("Necesitás \(hours) horas de OT para cubrir el saldo negativo.", "You need \(hours) hours of OT to cover the negative balance."))
                    .font(DincrFont.caption.weight(.semibold)).foregroundStyle(OwnerColor.onHero)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("\(idPrefix).status.otHours")
            }
            if !showsJarvis, status.headline == .safeToSpend, let takenOut = resultNote(status) {
                Text(takenOut).font(DincrFont.caption).foregroundStyle(OwnerColor.onHero2)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("\(idPrefix).status.resultNote")
            }
            if !showsJarvis, let dollars {
                Text(tx("Gastos incluye ≈ \(format.string(dollars)) estimado en dólares.", "Expenses include ≈ \(format.string(dollars)) estimated in dollars."))
                    .font(DincrFont.caption).foregroundStyle(OwnerColor.onHero2)
                    .accessibilityIdentifier("\(idPrefix).status.dollars")
            }
        }
    }

    /// Result = income − expenses − what else this line names, so the figures on screen add up.
    private func resultNote(_ status: HomeStatus) -> String? {
        var parts: [String] = []
        if let paid = status.debtPaid { parts.append(tx("\(format.string(paid)) pagados a deudas", "\(format.string(paid)) paid to debts")) }
        if let saved = status.automaticSaved { parts.append(tx("\(format.string(saved)) de ahorro automático", "\(format.string(saved)) of automatic savings")) }
        guard !parts.isEmpty else { return nil }
        return tx("El resultado también resta ", "The result also subtracts ") + parts.joined(separator: tx(" y ", " and ")) + "."
    }

    @ViewBuilder private func facts(_ status: HomeStatus) -> some View {
        fact(tx("Ingresos", "Income"), status.income, sign: .income, unknown: tx("Sin registrar", "Not recorded"))
        fact(tx("Gastos", "Expenses"), dollars.map { (status.expenses ?? 0) + $0 } ?? status.expenses, sign: .expense, unknown: tx("Sin registrar", "Not recorded"))
        if status.headline == .safeToSpend {
            fact(status.cycle == nil ? tx("Resultado del mes", "Month result") : tx("Resultado del corte", "Statement result"), status.result.map { $0 - (dollars ?? 0) }, sign: .none, unknown: "—")
        }
    }

    private func fact(_ label: String, _ value: Decimal?, sign: MoneyFormat.Sign, unknown: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(DincrFont.caption).foregroundStyle(OwnerColor.onHero2)
            if value == nil {
                Text(unknown).font(DincrFont.bodySmall.weight(.semibold)).foregroundStyle(OwnerColor.onHero2)
            } else {
                amount(value, sign: sign, font: DincrFont.bodySmall.weight(.semibold).monospacedDigit())
            }
        }
        .accessibilityElement(children: .combine)
    }

    /// `MoneyText`'s text and spoken label on the hero's color.
    private func amount(_ value: Decimal?, sign: MoneyFormat.Sign, font: Font) -> some View {
        Text(value.map { format.string($0, sign: sign) } ?? "—")
            .font(font)
            .foregroundStyle(OwnerColor.onHero)
            .lineLimit(1)
            .minimumScaleFactor(0.6)
            .accessibilityLabel(value.map { format.spoken($0, sign: sign) } ?? tx("sin dato", "no data"))
    }

    @ViewBuilder
    private var actions: some View {
        Button { register(.expense) } label: {
            Label(tx("Gasto", "Expense"), systemImage: "plus")
        }
        .buttonStyle(OwnerHeroButtonStyle(prominent: true))
        .accessibilityLabel(tx("Registrar gasto", "Record expense"))
        .accessibilityIdentifier("\(idPrefix).addExpense")
        Button { register(.income) } label: {
            Label(tx("Ingreso", "Income"), systemImage: "plus")
        }
        .buttonStyle(OwnerHeroButtonStyle(prominent: false))
        .accessibilityLabel(tx("Registrar ingreso", "Record income"))
        .accessibilityIdentifier("\(idPrefix).addIncome")
        // Goals and savings: VIP and the Owner (OW-2, VIP-1).
        if showsJarvis || showsGoals {
            NavigationLink { GoalsView() } label: {
                Label(tx("Ahorros", "Savings"), systemImage: "target")
            }
            .accessibilityLabel(tx("Metas y ahorros", "Goals and savings"))
            .buttonStyle(OwnerHeroButtonStyle(prominent: false))
            .accessibilityIdentifier("\(idPrefix).goals")
        }
        // The one way into JARVIS from Hoy (spec OW-1): the Owner's Hoy only.
        if showsJarvis {
            NavigationLink(value: ProfileRoute.jarvis) {
                Label("JARVIS", systemImage: "sparkles")
            }
            .buttonStyle(OwnerHeroButtonStyle(prominent: false))
            .accessibilityIdentifier("owner.home.jarvis")
        }
    }
}

/// The Owner's hero entries: the icon over a one-word title, so four fit on one row.
private struct HeroTileLabelStyle: LabelStyle {
    func makeBody(configuration: Configuration) -> some View {
        VStack(spacing: 2) {
            configuration.icon.font(.system(size: 16, weight: .semibold))
            configuration.title.font(DincrFont.caption.weight(.semibold)).lineLimit(1).minimumScaleFactor(0.8)
        }
        .padding(.vertical, DincrSpacing.s2)
    }
}

/// The frame of Hoy: the hero, then the blocks on a sheet with rounded top corners. The hero's color
/// stays behind the top (also when pulled down), and the sheet covers it while scrolling.
struct HomeHeroScreen<Hero: View, Sheet: View>: View {
    let id: String
    @ViewBuilder let hero: Hero
    @ViewBuilder let sheet: Sheet

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                // Its own color too: at a large text size it is taller than the fixed color behind it.
                hero.background(OwnerColor.hero)
                VStack(alignment: .leading, spacing: DincrSpacing.s4) { sheet }
                    .padding(.horizontal, DincrSpacing.s4)
                    .padding(.top, DincrSpacing.s2)
                    .padding(.bottom, DincrSpacing.s8)
                    .frame(maxWidth: 640)
                    .frame(maxWidth: .infinity)
                    .background(OwnerColor.backgroundMiddle, in: UnevenRoundedRectangle(topLeadingRadius: 24, topTrailingRadius: 24, style: .continuous))
                    // The sheet's rounded corners keep the hero's color behind them at any height.
                    .background(alignment: .top) { OwnerColor.hero.frame(height: 24) }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(id)
        }
        .background(alignment: .top) {
            OwnerColor.backgroundMiddle.ignoresSafeArea()
                .overlay(alignment: .top) { OwnerColor.hero.frame(height: 480).ignoresSafeArea() }
        }
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(OwnerColor.hero, for: .navigationBar)
        .toolbarBackground(.visible, for: .navigationBar)
        .toolbarColorScheme(.dark, for: .navigationBar)
    }
}
