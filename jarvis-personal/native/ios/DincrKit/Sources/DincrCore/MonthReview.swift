import Foundation

// RV-1 — Revisión del mes, easy to understand: the month that just closed in three short cards.
// How it went (what was left, compared with the month before), what you achieved (debt paid and
// money put aside) and one thing to do this month. Every figure is the month's own summary
// (`/free/monthly-summary`, the same Resumen del mes counts); this file only words it. Unknown figures
// are not read as 0: the card says nothing about them. Android twin: `MonthReview.kt`.

public enum MonthReview {
    public struct Card: Equatable, Sendable {
        public let title: String
        public let lines: [String]
    }

    /// What was left: income minus spending and debt payments; nil while income or spending is unknown.
    public static func left(_ summary: MonthlySummary) -> Decimal? {
        guard let income = summary.income, let expenses = summary.expenses else { return nil }
        return income - expenses - (summary.debtPaid ?? 0)
    }

    /// The three cards for the month `summary` (with the month before it, when known).
    public static func cards(_ summary: MonthlySummary, previous: MonthlySummary?, format: MoneyFormat,
                             language: AppLanguage = .current) -> [Card] {
        let month = OwnerReading.monthLabel(summary.period ?? "", language: language)
        let left = left(summary)
        var how: [String] = []
        if let left {
            how.append(left >= 0 ? language.pick("Te sobraron \(format.string(left)).", "You had \(format.string(left)) left over.")
                                 : language.pick("Salió \(format.string(-left)) más de lo que entró.", "\(format.string(-left)) more went out than came in."))
            if let before = previous.flatMap(Self.left) {
                let change = left - before
                if change > 0 { how.append(language.pick("Es \(format.string(change)) mejor que el mes anterior.", "That is \(format.string(change)) better than the month before.")) }
                else if change < 0 { how.append(language.pick("Es \(format.string(-change)) menos que el mes anterior.", "That is \(format.string(-change)) less than the month before.")) }
                else { how.append(language.pick("Igual que el mes anterior.", "The same as the month before.")) }
            }
        } else {
            how.append(language.pick("Faltan los ingresos o los gastos de este mes para saberlo.", "This month’s income or expenses are missing to know it."))
        }

        var achieved: [String] = []
        if let debt = summary.debtPaid, debt > 0 { achieved.append(language.pick("Pagaste \(format.string(debt)) de deudas.", "You paid \(format.string(debt)) of debts.")) }
        if let saved = summary.saved?.total, saved > 0 { achieved.append(language.pick("Guardaste \(format.string(saved)).", "You put aside \(format.string(saved)).")) }
        if achieved.isEmpty { achieved.append(language.pick("Este mes no hubo pagos de deudas ni ahorro registrados.", "No debt payments or savings were recorded this month.")) }

        return [
            Card(title: language.pick("Cómo te fue en \(month)", "How \(month) went"), lines: how),
            Card(title: language.pick("Lo que lograste", "What you achieved"), lines: achieved),
            Card(title: language.pick("Para este mes", "For this month"), lines: [action(summary, left: left, format: format, language: language)]),
        ]
    }

    /// One thing to do, from the month's own figures (a rule, not advice).
    static func action(_ summary: MonthlySummary, left: Decimal?, format: MoneyFormat, language: AppLanguage) -> String {
        if let left, left < 0 {
            if let top = summary.topCategory, let name = top.category, let amount = top.amount {
                return language.pick("Tu gasto más grande fue \(name) (\(format.string(amount))). Bajarlo un poco es lo que más ayuda.",
                                     "Your biggest spending was \(name) (\(format.string(amount))). Lowering it a little helps the most.")
            }
            return language.pick("Revisá en qué se fue la plata en Resumen del mes y elegí un gasto para bajar.",
                                 "Check where the money went in Monthly summary and pick one expense to lower.")
        }
        if (summary.saved?.total ?? 0) <= 0 {
            return language.pick("Apenas entre tu salario, apartá algo para tu Salvavidas o una meta, aunque sea poco.",
                                 "As soon as your pay comes in, put something aside for your emergency fund or a goal, even a little.")
        }
        return language.pick("Seguí igual: mantené lo que guardás y tus pagos de deudas al día.",
                             "Keep it up: keep saving and keep your debt payments up to date.")
    }

    /// The month that just closed (`YYYY-MM`) and the one before it.
    public static func closedMonths(today: Date, calendar: Calendar = Calendar(identifier: .gregorian)) -> (closed: String, before: String) {
        func period(_ back: Int) -> String {
            let date = calendar.date(byAdding: .month, value: -back, to: today) ?? today
            let parts = calendar.dateComponents([.year, .month], from: date)
            return String(format: "%04d-%02d", parts.year ?? 0, parts.month ?? 0)
        }
        return (period(1), period(2))
    }
}
