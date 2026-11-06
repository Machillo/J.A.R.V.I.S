import Charts
import DincrCore
import SwiftUI

/// Income vs expenses per month: grouped bars, two validated series colors, legend always,
/// value labels on selection, and a table alternative (DESIGN_SYSTEM.md §8).
public struct IncomeExpenseChart: View {
    let months: [MonthTotals]
    let language: AppLanguage
    @Environment(\.moneyFormat) private var format
    @State private var showsTable = false

    public init(months: [MonthTotals], language: AppLanguage = .current) {
        self.months = months; self.language = language
    }

    private var incomeLabel: String { language.pick("Ingresos", "Income") }
    private var expenseLabel: String { language.pick("Gastos", "Expenses") }

    public var body: some View {
        VStack(alignment: .leading, spacing: DincrSpacing.s3) {
            Chart {
                ForEach(months) { month in
                    BarMark(x: .value("Mes", shortMonth(month.month)), y: .value("Monto", NSDecimalNumber(decimal: month.income).doubleValue), width: .ratio(0.8))
                        .foregroundStyle(by: .value("Serie", incomeLabel))
                        .position(by: .value("Serie", incomeLabel), axis: .horizontal, span: .ratio(0.9))
                        .clipShape(UnevenRoundedRectangle(topLeadingRadius: 4, topTrailingRadius: 4))
                    BarMark(x: .value("Mes", shortMonth(month.month)), y: .value("Monto", NSDecimalNumber(decimal: month.expenses).doubleValue), width: .ratio(0.8))
                        .foregroundStyle(by: .value("Serie", expenseLabel))
                        .position(by: .value("Serie", expenseLabel), axis: .horizontal, span: .ratio(0.9))
                        .clipShape(UnevenRoundedRectangle(topLeadingRadius: 4, topTrailingRadius: 4))
                }
            }
            .chartForegroundStyleScale([incomeLabel: DincrColor.chartIncome, expenseLabel: DincrColor.chartExpense])
            .chartLegend(position: .top, alignment: .leading, spacing: DincrSpacing.s3)
            .chartYAxis {
                AxisMarks(position: .leading, values: .automatic(desiredCount: 3)) { value in
                    AxisGridLine().foregroundStyle(OwnerColor.border)
                    AxisValueLabel {
                        if let number = value.as(Double.self) { Text(compact(number)).font(DincrFont.caption).foregroundStyle(.dincrTextMuted) }
                    }
                }
            }
            .chartXAxis {
                AxisMarks { _ in AxisValueLabel().font(DincrFont.caption).foregroundStyle(.dincrTextMuted) }
            }
            .frame(height: 180)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(title)
            .accessibilityValue(summary)

            DisclosureGroup(isExpanded: $showsTable) {
                VStack(spacing: DincrSpacing.s2) {
                    ForEach(months) { month in
                        HStack {
                            Text(shortMonth(month.month)).font(DincrFont.bodySmall).foregroundStyle(.dincrText2)
                            Spacer()
                            MoneyText(month.income, sign: .income, font: DincrFont.bodySmall.monospacedDigit())
                            MoneyText(month.expenses, sign: .expense, font: DincrFont.bodySmall.monospacedDigit())
                                .frame(minWidth: 96, alignment: .trailing)
                        }
                        .accessibilityElement(children: .combine)
                    }
                }
                .padding(.top, DincrSpacing.s2)
            } label: {
                Text(language.pick("Ver como tabla", "Show as table")).font(DincrFont.label).foregroundStyle(.dincrTint)
            }
            .tint(OwnerColor.accent)
        }
    }

    private var title: String {
        if months.count == 1, let month = months.first {
            return language.pick("Ingresos y gastos de \(shortMonth(month.month))", "Income and expenses for \(shortMonth(month.month))")
        }
        return language.pick("Ingresos y gastos de los últimos \(months.count) meses", "Income and expenses for the last \(months.count) months")
    }

    private var summary: String {
        months.map { "\(shortMonth($0.month)): \(incomeLabel) \(format.spoken($0.income)), \(expenseLabel) \(format.spoken($0.expenses))" }
            .joined(separator: "; ")
    }

    private func shortMonth(_ period: String) -> String {
        let parts = period.split(separator: "-")
        guard parts.count == 2, let month = Int(parts[1]), (1...12).contains(month) else { return period }
        let names = language == .spanish
            ? ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]
            : ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return names[month - 1]
    }

    private func compact(_ value: Double) -> String {
        value >= 1_000_000 ? String(format: "%.1fM", value / 1_000_000) : value >= 1_000 ? "\(Int(value / 1_000))k" : "\(Int(value))"
    }
}

/// Where the money goes: one hue, sorted, direct value labels, no legend.
public struct CategoryBars: View {
    let categories: [CategoryAmount]
    let limit: Int

    public init(categories: [CategoryAmount], limit: Int = 5) {
        self.categories = categories; self.limit = limit
    }

    public var body: some View {
        let shown = Array(categories.sorted { $0.amount > $1.amount }.prefix(limit))
        let top = shown.first.map { NSDecimalNumber(decimal: $0.amount).doubleValue } ?? 1
        VStack(spacing: DincrSpacing.s3) {
            ForEach(shown) { item in
                VStack(alignment: .leading, spacing: 6) {
                    HStack {
                        Text(CategoryStyle.label(item.category)).font(DincrFont.bodySmall).foregroundStyle(.dincrText)
                        Spacer()
                        MoneyText(item.amount, font: DincrFont.bodySmall.weight(.semibold).monospacedDigit())
                    }
                    GeometryReader { proxy in
                        Capsule().fill(DincrColor.chartExpense)
                            .frame(width: max(6, proxy.size.width * NSDecimalNumber(decimal: item.amount).doubleValue / max(top, 1)))
                    }
                    .frame(height: 6)
                    .accessibilityHidden(true)
                }
                .accessibilityElement(children: .combine)
            }
        }
    }
}

/// Category presentation: SF Symbol and display label. Category values are backend data;
/// this only chooses how to draw them.
public enum CategoryStyle {
    public static func symbol(for category: String?, kind: Movement.Kind) -> String {
        if kind == .income { return "arrow.down.left" }
        switch category?.lowercased() ?? "" {
        case "vivienda", "alquiler": return "house"
        case "comida", "supermercado": return "cart"
        case "restaurante": return "fork.knife"
        case "transporte": return "bus"
        case "gasolina": return "fuelpump"
        case "servicios", "internet", "teléfono": return "bolt"
        case "salud": return "cross.case"
        case "entretenimiento": return "ticket"
        case "compras": return "bag"
        case "seguros": return "shield"
        case "deporte": return "figure.run"
        case "mascotas": return "pawprint"
        default: return "arrow.up.right"
        }
    }

    public static func label(_ category: String?) -> String {
        guard let category, !category.isEmpty else { return AppLanguage.current.pick("Sin categoría", "Uncategorized") }
        // Categories are stored in Spanish (the backend's catalog); in English they read in English.
        return AppLanguage.current.pick(category, english[category] ?? category)
    }

    /// The app's own category names in English. Anything else (a bank's or the user's) stays as written.
    static let english: [String: String] = [
        "Comida": "Food",
        "Vivienda": "Housing",
        "Servicios": "Utilities",
        "Internet": "Internet",
        "Teléfono": "Phone",
        "Transporte": "Transport",
        "Gasolina": "Fuel",
        "Restaurante": "Restaurants",
        "Salud": "Health",
        "Entretenimiento": "Entertainment",
        "Compras": "Shopping",
        "Seguros": "Insurance",
        "Deporte": "Sports",
        "Mascotas": "Pets",
        "Otros": "Other",
        "Salario": "Salary",
        "Boleta de pago": "Pay stub",
        "Bono": "Bonus",
        "Reembolso": "Refund",
        "Otros ingresos": "Other income",
        "Supermercado": "Groceries",
        "Horas extra": "Overtime",
        "Deudas": "Debts",
        "Ahorro": "Savings",
        "Educación": "Education",
        "Ropa": "Clothing",
        "Viajes": "Travel",
        "Suscripciones": "Subscriptions"
    ]
}
