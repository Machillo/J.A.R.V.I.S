import DincrCore
import DincrDesign
import SwiftUI

/// The top of the Owner's Hoy: greeting, the day's key figure and the main actions on one solid color
/// (DESIGN.md → Owner identity). Read-only figures: the same `HomeStatus` the blocks below use, and
/// unknown stays "—" (the block below says what DINCR needs).
struct OwnerHomeHero: View {
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
            .accessibilityIdentifier("owner.home.greeting")
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
                    .accessibilityIdentifier("owner.home.status.amount")
                if let cycle {
                    Text(cycle).font(DincrFont.caption).foregroundStyle(OwnerColor.onHero2)
                        .accessibilityIdentifier("owner.home.status.cycle")
                }
            }
            HStack(alignment: .top, spacing: DincrSpacing.s4) {
                fact(tx("Ingresos", "Income"), status.income, sign: .income, unknown: tx("Sin registrar", "Not recorded"))
                fact(tx("Gastos", "Expenses"), status.expenses, sign: .expense, unknown: tx("Sin registrar", "Not recorded"))
                if status.headline == .safeToSpend {
                    fact(status.cycle == nil ? tx("Resultado del mes", "Month result") : tx("Resultado del corte", "Statement result"), status.result, sign: .none, unknown: "—")
                }
            }
            .accessibilityIdentifier("owner.home.status.facts")
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
        .accessibilityIdentifier("owner.home.addExpense")
        Button { register(.income) } label: {
            Label(tx("Ingreso", "Income"), systemImage: "plus")
        }
        .buttonStyle(OwnerHeroButtonStyle(prominent: false))
        .accessibilityLabel(tx("Registrar ingreso", "Record income"))
        .accessibilityIdentifier("owner.home.addIncome")
        // The one way into JARVIS from Hoy (spec OW-1).
        NavigationLink(value: ProfileRoute.jarvis) {
            Label("JARVIS", systemImage: "sparkles")
        }
        .buttonStyle(OwnerHeroButtonStyle(prominent: false))
        .accessibilityIdentifier("owner.home.jarvis")
    }
}
