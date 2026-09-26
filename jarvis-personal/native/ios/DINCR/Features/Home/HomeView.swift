import DincrCore
import DincrDesign
import SwiftUI

/// PARITY C1 — Free overview. One key figure (available this month, from the backend), the
/// month's income and expenses, the 6-month comparison and where the money goes. Every number
/// is a backend value; nothing is derived here.
struct HomeView: View {
    @Environment(AppModel.self) private var model
    let openMovements: () -> Void
    @State private var state: LoadState<FreeDashboard> = .loading

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: DincrSpacing.s4) {
                switch state {
                case .loading:
                    SkeletonView(rows: 3)
                case .failed(let message):
                    ErrorStateView(message: message) { Task { await load() } }
                case .loaded(let dashboard):
                    content(dashboard)
                }
            }
            .padding(.horizontal, DincrSpacing.s4)
            .padding(.bottom, DincrSpacing.s6)
            .frame(maxWidth: 600)
            .frame(maxWidth: .infinity)
        }
        .dincrScreenBackground()
        .navigationTitle(tx("Hola, \(model.profile?.firstName ?? "")", "Hi, \(model.profile?.firstName ?? "")"))
        .refreshable { await load() }
        .task { if case .loading = state { await load() } }
    }

    @ViewBuilder
    private func content(_ dashboard: FreeDashboard) -> some View {
        let empty = dashboard.monthlyHistory.isEmpty && dashboard.categories.isEmpty && dashboard.income == 0 && dashboard.expenses == 0

        VStack(alignment: .leading, spacing: DincrSpacing.s2) {
            Text(tx("Disponible este mes", "Available this month")).font(DincrFont.label).foregroundStyle(DincrColor.text2)
            MoneyText(dashboard.available, font: DincrFont.displayAmount)
            HStack(spacing: DincrSpacing.s4) {
                figure(tx("Ingresos", "Income"), dashboard.income, sign: .income)
                figure(tx("Gastos", "Expenses"), dashboard.expenses, sign: .expense)
            }
            .padding(.top, DincrSpacing.s2)
            if let debt = dashboard.debtBalance, debt > 0 {
                Divider().overlay(DincrColor.line).padding(.vertical, DincrSpacing.s1)
                HStack {
                    Text(tx("Deuda pendiente", "Outstanding debt")).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                    Spacer()
                    MoneyText(debt, font: DincrFont.bodySmall.weight(.semibold).monospacedDigit())
                }
                .accessibilityElement(children: .combine)
            }
        }
        .dincrCard()
        .accessibilityElement(children: .contain)

        if empty {
            EmptyStateView(
                symbol: "tray",
                title: tx("Todavía no hay movimientos", "No transactions yet"),
                message: tx("Cuando registrés ingresos y gastos, acá verás tu mes y en qué se va el dinero.", "When you record income and expenses, you’ll see your month and where the money goes here.")
            ) {
                Button(tx("Agregar movimiento", "Add transaction"), action: openMovements).buttonStyle(.dincrPrimary)
            }
        } else {
            section(tx("Ingresos y gastos", "Income and expenses")) {
                IncomeExpenseChart(months: dashboard.monthlyHistory)
            }
            section(tx("En qué se va el dinero", "Where the money goes")) {
                if dashboard.categories.isEmpty {
                    Text(tx("Cuando registrés gastos, los agruparemos acá.", "When you record expenses, we’ll group them here."))
                        .font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2)
                } else {
                    CategoryBars(categories: dashboard.categories)
                }
            }
            Button(action: openMovements) {
                HStack {
                    Text(tx("Ver movimientos", "See transactions")).font(DincrFont.title2)
                    Spacer()
                    Image(systemName: "chevron.forward").accessibilityHidden(true)
                }
                .foregroundStyle(DincrColor.tint)
                .frame(minHeight: 44)
            }
            .dincrCard(padding: DincrSpacing.s3)
        }
    }

    private func figure(_ label: String, _ amount: Decimal, sign: MoneyFormat.Sign) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
            MoneyText(amount, sign: sign)
        }
        .accessibilityElement(children: .combine)
    }

    private func section<Content: View>(_ title: String, @ViewBuilder _ content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s3) {
            Text(title).font(DincrFont.title2).foregroundStyle(DincrColor.text).accessibilityAddTraits(.isHeader)
            content()
        }
        .dincrCard()
        .padding(.top, DincrSpacing.s2)
    }

    private func load() async {
        do {
            state = .loaded(try await model.service.freeDashboard())
        } catch let error as APIError {
            state = .failed(error.message)
        } catch AuthError.signedOut {
            await model.signOut()
        } catch {
            state = .failed(tx("No pudimos cargar tu resumen.", "We couldn’t load your overview."))
        }
    }
}

enum LoadState<Value: Equatable>: Equatable {
    case loading
    case failed(String)
    case loaded(Value)
}
