import Foundation

/// E04 / E05 — what Movimientos → Análisis → Resumen del mes draws from the month's own summary
/// (`GET /user-product/free/monthly-summary`), nothing else. E04 compares the selected month's income
/// and expenses as bars; E05 splits its expenses by category as a donut. The amounts above them stay
/// as the readable alternative. An unknown amount is never drawn as zero, no category or amount is
/// made up, and a share exists only when every category is known (`Composition`). The donut's
/// segments are not links yet (a filtered movement list needs P5.1). Android: `SummaryVisuals.kt`.
public enum SummaryVisuals {
    /// E04: the month's income and expenses.
    public enum Flow: Equatable, Sendable {
        /// Both are known and something was recorded: two bars.
        case bars(MonthTotals)
        /// Income or expenses unknown: no bars (one bar alone is not a comparison, an unknown is not 0).
        case incomplete
        /// Both known and zero: nothing was recorded this month.
        case empty
    }

    public static func flow(_ summary: MonthlySummary) -> Flow {
        guard let income = summary.income, let expenses = summary.expenses else { return .incomplete }
        if income == 0 && expenses == 0 { return .empty }
        return .bars(MonthTotals(month: summary.period ?? "", income: income, expenses: expenses))
    }

    /// E05: the month's expenses by category, in the backend's order (largest first). A category
    /// without an amount stays unknown, so the donut and its shares are not drawn.
    public static func categories(_ summary: MonthlySummary, language: AppLanguage = .current) -> Composition {
        Composition(categoryItems(summary, language: language))
    }

    static func categoryItems(_ summary: MonthlySummary, language: AppLanguage) -> [CompositionItem] {
        (summary.categories ?? []).enumerated().map { index, row in
            let label = row.category.flatMap { $0.isEmpty ? nil : $0 } ?? language.pick("Sin categoría", "Uncategorized")
            return CompositionItem(id: "\(index)-\(label)", label: label, value: row.amount)
        }
    }

    /// "¿De dónde entró?": the period's income by category (`income_categories`, largest first).
    public static func incomeSources(_ summary: MonthlySummary, language: AppLanguage = .current) -> Composition {
        Composition((summary.incomeCategories ?? []).enumerated().map { index, row in
            let label = row.category.flatMap { $0.isEmpty ? nil : $0 } ?? language.pick("Sin categoría", "Uncategorized")
            return CompositionItem(id: "in-\(index)-\(label)", label: label, value: row.amount)
        })
    }

    /// "¿A dónde se fue?": spending by category, then debt payments and what was saved, each only
    /// when the backend sent it above zero (an unknown amount is never drawn as zero).
    public static func outflows(_ summary: MonthlySummary, language: AppLanguage = .current) -> Composition {
        var items = categoryItems(summary, language: language)
        if let debt = summary.debtPaid, debt > 0 {
            items.append(CompositionItem(id: "out-debts", label: language.pick("Pagos de deudas", "Debt payments"), value: debt))
        }
        if let saved = summary.saved?.total, saved > 0 {
            items.append(CompositionItem(id: "out-saved", label: language.pick("Ahorro", "Savings"), value: saved))
        }
        return Composition(items)
    }

    public static func flowNotice(_ flow: Flow, language: AppLanguage = .current) -> String? {
        switch flow {
        case .bars: nil
        case .incomplete: language.pick("Faltan los ingresos o los gastos de este mes, así que no los comparamos.",
                                        "This month’s income or expenses are missing, so they aren’t compared.")
        case .empty: language.pick("Todavía no hay ingresos ni gastos registrados en este mes.",
                                   "No income or expenses recorded this month yet.")
        }
    }
}
