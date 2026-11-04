import DincrCore
import DincrDesign
import SwiftUI

/// The top of Hoy in every plan: greeting, the day's key figure and the main actions on one solid color
/// (DESIGN.md). Read-only figures: the same `HomeStatus` the blocks below use, and unknown stays "—"
/// (the block below says what DINCR needs). JARVIS appears only when the caller is the Owner's Hoy.
struct HomeHero: View {
    var idPrefix = "home"
    var showsJarvis = false
    let greeting: String
    let name: String?
    let status: HomeStatus?
    let cycle: String?
    let register: (Movement.Kind) -> Void
    @Environment(\.moneyFormat) private var format

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
            ViewThatFits(in: .horizontal) {
                HStack(spacing: DincrSpacing.s2) { actions }
                VStack(spacing: DincrSpacing.s2) { actions }
            }
        }
        .padding(.horizontal, DincrSpacing.s4)
        .padding(.top, DincrSpacing.s2)
        .padding(.bottom, DincrSpacing.s6)
        .frame(maxWidth: 640, alignment: .leading)
        .frame(maxWidth: .infinity)
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
        }
    }

    @ViewBuilder private func facts(_ status: HomeStatus) -> some View {
        fact(tx("Ingresos", "Income"), status.income, sign: .income, unknown: tx("Sin registrar", "Not recorded"))
        fact(tx("Gastos", "Expenses"), status.expenses, sign: .expense, unknown: tx("Sin registrar", "Not recorded"))
        if status.headline == .safeToSpend {
            fact(status.cycle == nil ? tx("Resultado del mes", "Month result") : tx("Resultado del corte", "Statement result"), status.result, sign: .none, unknown: "—")
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
