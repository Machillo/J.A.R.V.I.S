import Foundation

// FA-1 — Movimientos → Análisis → Análisis financiero (VIP and the Owner): the last twelve months
// of the figures Resumen del mes shows (`GET /user-product/vip/financial-analysis`), read in plain
// words for people who do not know finance. The backend counts; this file only averages the months
// that can be compared and writes the sentences, so both apps say the same thing. Nothing here is
// advice: it describes the user's own numbers. Android twin: `FinancialAnalysis.kt`.

/// `GET /user-product/vip/financial-analysis`.
public struct FinancialAnalysis: Decodable, Sendable, Equatable {
    public struct Month: Decodable, Sendable, Equatable, Identifiable {
        public let period: String
        public let income: Decimal?
        public let expenses: Decimal?
        public let debtPaid: Decimal?
        public let saved: Decimal?
        /// The month in course: it is not over, so it is never averaged.
        public let partial: Bool?
        public var id: String { period }

        public init(period: String, income: Decimal?, expenses: Decimal?, debtPaid: Decimal? = 0, saved: Decimal? = 0, partial: Bool = false) {
            self.period = period; self.income = income; self.expenses = expenses; self.debtPaid = debtPaid; self.saved = saved; self.partial = partial
        }
    }

    /// This month's spending in a category beside its average in the last complete months
    /// (`average` nil: there is no earlier month to compare with).
    public struct Category: Decodable, Sendable, Equatable {
        public let category: String?
        public let current: Decimal?
        public let average: Decimal?

        public init(category: String?, current: Decimal?, average: Decimal?) {
            self.category = category; self.current = current; self.average = average
        }
    }

    public let months: [Month]
    public let categories: [Category]?

    public init(months: [Month], categories: [Category]? = nil) {
        self.months = months; self.categories = categories
    }
}

extension DincrService {
    /// VIP and the Owner. A read: it never writes.
    public func financialAnalysis() async throws -> FinancialAnalysis { try await client.get("/user-product/vip/financial-analysis") }
}

public enum FinancialReading {
    /// An average month: the complete months where both income and spending were recorded (a month
    /// without one of them is missing data, not a month without money).
    public struct Normal: Sendable, Equatable {
        public let months: Int
        public let income: Decimal
        public let expenses: Decimal
        public let debtPaid: Decimal
        public let saved: Decimal
        /// What is left: income minus spending and debt payments (saving comes out of it).
        public var left: Decimal { income - expenses - debtPaid }
    }

    public static func normal(_ analysis: FinancialAnalysis) -> Normal? {
        let counted = analysis.months.filter { $0.partial != true && ($0.income ?? 0) > 0 && ($0.expenses ?? 0) > 0 }
        guard !counted.isEmpty else { return nil }
        func average(_ value: (FinancialAnalysis.Month) -> Decimal?) -> Decimal {
            rounded(counted.reduce(Decimal(0)) { $0 + (value($1) ?? 0) } / Decimal(counted.count), places: 2)
        }
        return Normal(months: counted.count, income: average(\.income), expenses: average(\.expenses),
                      debtPaid: average(\.debtPaid), saved: average(\.saved))
    }

    /// How many of every 100 that come in: rounded to a whole number; nil without income.
    public static func per100(_ part: Decimal, of whole: Decimal) -> Int? {
        guard whole > 0 else { return nil }
        return NSDecimalNumber(decimal: rounded(part * 100 / whole, places: 0)).intValue
    }

    /// The months the bars draw: the ones with something recorded (an empty month is not drawn as 0).
    public static func chartMonths(_ analysis: FinancialAnalysis) -> [MonthTotals] {
        analysis.months.compactMap { month in
            guard let income = month.income, let expenses = month.expenses, income > 0 || expenses > 0 else { return nil }
            return MonthTotals(month: month.period, income: income, expenses: expenses, debtPaid: month.debtPaid)
        }
    }

    /// The categories where this month already went above the average, the largest difference first
    /// (at most `limit`). The month is not over, so a lower amount says nothing yet and is not listed.
    public static func rises(_ analysis: FinancialAnalysis, limit: Int = 3) -> [FinancialAnalysis.Category] {
        let above = (analysis.categories ?? []).filter { row in
            guard let current = row.current, let average = row.average else { return false }
            return current > average
        }
        return Array(above.sorted { ($0.current! - $0.average!) > ($1.current! - $1.average!) }.prefix(limit))
    }

    /// Whether there is an earlier month to compare this one with.
    public static func canCompare(_ analysis: FinancialAnalysis) -> Bool {
        (analysis.categories ?? []).contains { $0.average != nil }
    }

    // MARK: Sentences

    public static func leftSentence(_ normal: Normal, format: MoneyFormat, language: AppLanguage = .current) -> String {
        let left = normal.left
        if left > 0 { return language.pick("En un mes normal te sobran \(format.string(left)).", "In a normal month you have \(format.string(left)) left over.") }
        if left < 0 {
            return language.pick("En un mes normal sale \(format.string(-left)) más de lo que entra.",
                                 "In a normal month \(format.string(-left)) more goes out than comes in.")
        }
        return language.pick("En un mes normal sale lo mismo que entra.", "In a normal month as much goes out as comes in.")
    }

    public static func leftExplanation(_ normal: Normal, format: MoneyFormat, language: AppLanguage = .current) -> String {
        let months = normal.months == 1 ? language.pick("tu último mes completo", "your last complete month")
            : language.pick("tus últimos \(normal.months) meses completos", "your last \(normal.months) complete months")
        if normal.debtPaid > 0 {
            return language.pick(
                "Entra \(format.string(normal.income)), gastás \(format.string(normal.expenses)) y pagás \(format.string(normal.debtPaid)) de deudas. Es el promedio de \(months).",
                "\(format.string(normal.income)) comes in, you spend \(format.string(normal.expenses)) and pay \(format.string(normal.debtPaid)) of debts. It is the average of \(months).")
        }
        return language.pick("Entra \(format.string(normal.income)) y gastás \(format.string(normal.expenses)). Es el promedio de \(months).",
                             "\(format.string(normal.income)) comes in and you spend \(format.string(normal.expenses)). It is the average of \(months).")
    }

    public static func savedSentence(_ normal: Normal, language: AppLanguage = .current) -> String? {
        guard let share = per100(normal.saved, of: normal.income) else { return nil }
        if normal.saved <= 0 { return language.pick("Todavía no estás guardando parte de lo que entra.", "You are not saving part of what comes in yet.") }
        if share == 0 { return language.pick("Guardás menos de 1 de cada 100 que entran.", "You save less than 1 of every 100 that come in.") }
        return language.pick("Guardás \(share) de cada 100 que entran.", "You save \(share) of every 100 that come in.")
    }

    public static func savedExplanation(language: AppLanguage = .current) -> String {
        language.pick("Es lo que mandás a tus metas y a tu Salvavidas. Una referencia común es guardar al menos 10 de cada 100.",
                      "It is what you put into your goals and your emergency fund. A common reference is saving at least 10 of every 100.")
    }

    /// nil when no debts were paid in a normal month.
    public static func debtSentence(_ normal: Normal, language: AppLanguage = .current) -> String? {
        guard normal.debtPaid > 0, let share = per100(normal.debtPaid, of: normal.income) else { return nil }
        return language.pick("De cada 100 que entran, \(share) se van a pagar deudas.", "Of every 100 that come in, \(share) go to paying debts.")
    }

    public static func debtExplanation(language: AppLanguage = .current) -> String {
        language.pick("Mientras más bajo, más te queda libre para tus gastos y para guardar.",
                      "The lower it is, the more you have free for your spending and for saving.")
    }

    /// "Comida: ₡90 000 este mes · normalmente ₡60 000".
    public static func riseLine(_ row: FinancialAnalysis.Category, format: MoneyFormat, language: AppLanguage = .current) -> String {
        let name = row.category.flatMap { $0.isEmpty ? nil : $0 } ?? language.pick("Sin categoría", "Uncategorized")
        return language.pick("\(name): \(format.string(row.current ?? 0)) este mes · normalmente \(format.string(row.average ?? 0))",
                             "\(name): \(format.string(row.current ?? 0)) this month · usually \(format.string(row.average ?? 0))")
    }

    private static func rounded(_ value: Decimal, places: Int) -> Decimal {
        var copy = value, result = Decimal()
        NSDecimalRound(&result, &copy, places, .plain)
        return result
    }
}
