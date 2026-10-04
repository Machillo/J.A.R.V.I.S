import DincrCore
import DincrDesign
import SwiftUI

/// PARITY C2 — Basic overview (`/basic/dashboard`). Every figure is the backend's.
struct BasicHomeView: View {
    @Environment(AppModel.self) private var model
    let openMovements: () -> Void

    var body: some View {
        ScreenScroll(title: tx("Hola, \(model.profile?.firstName ?? "")", "Hi, \(model.profile?.firstName ?? "")")) {
            AsyncContent(fallback: tx("No pudimos cargar tu resumen.", "We couldn’t load your overview."), load: { try await model.service.basicDashboard() }) { dashboard, _ in
                BasicDashboardContent(dashboard: dashboard, openMovements: openMovements)
            }
        }
    }
}

private struct BasicDashboardContent: View {
    let dashboard: BasicDashboard
    let openMovements: () -> Void

    var body: some View {
                VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                    Text(tx("Balance del mes", "Balance this month")).font(DincrFont.label).foregroundStyle(DincrColor.text2)
                        .accessibilityIdentifier("home.basic")
                    MoneyText(dashboard.balance, font: DincrFont.displayAmount)
                    FigureRow(label: tx("Ingresos", "Income"), amount: dashboard.income, sign: .income)
                    FigureRow(label: tx("Gastos", "Expenses"), amount: dashboard.expenses, sign: .expense)
                    FigureRow(label: tx("Pagado a deudas", "Paid to debts"), amount: dashboard.debtPaid)
                }
                .dincrCard()
                HomePlanningLinks()

                if let debt = dashboard.debt, (debt.original ?? 0) > 0 {
                    VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                        SectionHeader(title: tx("Deudas", "Debts"))
                        FigureRow(label: tx("Saldo pendiente", "Outstanding"), amount: debt.remaining)
                        FigureRow(label: tx("Cuotas del mes", "Monthly payments"), amount: debt.monthly)
                        if let progress = debt.progress {
                            DincrProgressBar(fraction: progress / 100)
                            Text(tx("\(Int(progress.rounded()))% pagado", "\(Int(progress.rounded()))% paid")).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted)
                        }
                    }
                    .dincrCard()
                }
                VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                    SectionHeader(title: tx("Ahorro y metas", "Savings and goals"))
                    FigureRow(label: tx("Ahorrado en planes", "Saved in plans"), amount: dashboard.savings)
                    FigureRow(label: tx("Avance de metas", "Goal progress"), amount: dashboard.goals?.current)
                    if let progress = dashboard.goals?.progress { DincrProgressBar(fraction: progress / 100) }
                }
                .dincrCard()
                if let history = dashboard.monthlyHistory, !history.isEmpty {
                    VStack(alignment: .leading, spacing: DincrSpacing.s3) {
                        SectionHeader(title: tx("Ingresos y gastos", "Income and expenses"))
                        IncomeExpenseChart(months: history)
                    }
                    .dincrCard()
                }
                let categories = (dashboard.categories ?? []).compactMap { item in item.category.map { CategoryAmount(category: $0, amount: item.amount ?? 0) } }
                if !categories.isEmpty {
                    VStack(alignment: .leading, spacing: DincrSpacing.s3) {
                        SectionHeader(title: tx("En qué se va el dinero", "Where the money goes"))
                        CategoryBars(categories: categories)
                    }
                    .dincrCard()
                }
                Button(tx("Ver movimientos", "See transactions"), action: openMovements).buttonStyle(.dincrSecondary)
    }
}

/// PARITY C3/F4/F9 — VIP overview (`/vip/command-center`): the director's priority, safe to spend,
/// alerts, roadmap and the projection summary. Read-only: opening it never writes (no lifecycle
/// snapshot POST, unlike the Capacitor screen — §4.C).
struct VipHomeView: View {
    @Environment(AppModel.self) private var model
    let openMovements: () -> Void

    var body: some View {
        ScreenScroll(title: tx("Hola, \(model.profile?.firstName ?? "")", "Hi, \(model.profile?.firstName ?? "")")) {
            AsyncContent(fallback: tx("No pudimos cargar tu centro de mando.", "We couldn’t load your command center."), load: { try await model.service.commandCenter() }) { center, _ in
                CommandCenterContent(center: center)
            }
        }
    }
}

private struct CommandCenterContent: View {
    let center: CommandCenter

    var body: some View {
                VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                    Text(tx("Podés gastar con tranquilidad", "Safe to spend")).font(DincrFont.label).foregroundStyle(DincrColor.text2)
                    MoneyText(center.safeToSpend?.amount, font: DincrFont.displayAmount)
                        .accessibilityIdentifier("home.safeToSpend")
                    FigureRow(label: tx("Margen del mes", "Monthly margin"), amount: center.safeToSpend?.monthlyMargin)
                    // #292: next_45_days_minimum is the lowest balance expected in the next 45 days, not a commitment total.
                    FigureRow(label: tx("Saldo mínimo previsto (45 días)", "Lowest expected balance (45 days)"), amount: center.safeToSpend?.next45DaysMinimum)
                }
                .dincrCard()
                HomePlanningLinks()

                if let director = center.director {
                    VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                        SectionHeader(title: tx("Tu prioridad", "Your priority"))
                        if let headline = director.headline { Text(headline).font(DincrFont.body.weight(.semibold)).foregroundStyle(DincrColor.text) }
                        if let next = director.nextAction { Text(next).font(DincrFont.bodySmall).foregroundStyle(DincrColor.text2) }
                        if director.dataComplete == false {
                            Text(tx("Completá tu situación financiera para una recomendación más precisa.", "Complete your financial situation for a more precise recommendation."))
                                .font(DincrFont.caption).foregroundStyle(DincrColor.warning)
                        }
                    }
                    .dincrCard()
                }
                if let automation = center.automation, (automation.review ?? 0) > 0 {
                    NavigationLink { EmailMonitorView() } label: {
                        HubRow(symbol: "envelope.badge", title: tx("Avisos del correo por revisar", "Mail notices to review"),
                               subtitle: tx("\(automation.review ?? 0) pendientes", "\(automation.review ?? 0) pending"))
                    }
                    .buttonStyle(.plain)
                    .dincrCard(padding: DincrSpacing.s3)
                }
                let alerts = center.alerts ?? []
                if !alerts.isEmpty {
                    SectionHeader(title: tx("Alertas", "Alerts"))
                    ForEach(Array(alerts.enumerated()), id: \.offset) { _, alert in
                        DincrMessage(.financial(severity: alert.severity), title: alert.title ?? "",
                                     message: [alert.context, alert.action].compactMap { $0 }.joined(separator: " "))
                    }
                }
                let roadmap = center.roadmap ?? []
                if !roadmap.isEmpty {
                    VStack(alignment: .leading, spacing: DincrSpacing.s3) {
                        SectionHeader(title: tx("Tu hoja de ruta", "Your roadmap"))
                        ForEach(Array(roadmap.enumerated()), id: \.offset) { index, step in
                            HStack(alignment: .top, spacing: DincrSpacing.s3) {
                                Text("\(step.order ?? index + 1)").font(DincrFont.label).foregroundStyle(DincrColor.onTintContainer)
                                    .frame(width: 24, height: 24).background(DincrColor.tintContainer, in: Circle())
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(step.title ?? "").font(DincrFont.body.weight(.semibold))
                                    if let why = step.why { Text(why).font(DincrFont.caption).foregroundStyle(DincrColor.textMuted) }
                                }
                                Spacer(minLength: 0)
                                MoneyText(step.amount, font: DincrFont.bodySmall.monospacedDigit())
                            }
                            .accessibilityElement(children: .combine)
                        }
                    }
                    .dincrCard()
                }
                if let score = center.score, let value = score.value {
                    VStack(alignment: .leading, spacing: DincrSpacing.s2) {
                        SectionHeader(title: tx("Salud financiera", "Financial health"))
                        InfoRow(label: score.label ?? "", value: "\(value)/100")
                        DincrProgressBar(fraction: Double(value) / 100)
                    }
                    .dincrCard()
                }
                FinancialDisclaimer()
    }
}
