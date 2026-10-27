import Foundation

// How the Owner's figures read (Owner information clarity). One wording per concept, shared by
// every screen that shows it, so "Resumen del mes", "Análisis financiero" and "Tu plan del mes"
// never explain the same figure two ways. Wording only: every amount is the backend's.
// Android: `OwnerReading` (core/data OwnerReading.kt).

/// An inclusive date range (`YYYY-MM-DD`), as the backend sends it.
public struct DatePeriod: Decodable, Sendable, Equatable {
    public let start: String?
    public let end: String?
    public init(start: String?, end: String?) { self.start = start; self.end = end }
}

/// Gross payroll the Owner's ledger reports apart (never added to income): overtime, VGH, bonuses.
public struct PayrollAccrued: Decodable, Sendable, Equatable {
    public let overtimeGross: Decimal?
    public let vghGross: Decimal?
    public let bonusesGross: Decimal?
    public let totalGross: Decimal?

    enum CodingKeys: String, CodingKey { case overtimeGross, vghGross, bonusesGross, totalGross }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        overtimeGross = c.lenient(Decimal.self, .overtimeGross)
        vghGross = c.lenient(Decimal.self, .vghGross)
        bonusesGross = c.lenient(Decimal.self, .bonusesGross)
        totalGross = c.lenient(Decimal.self, .totalGross)
    }
}

public enum OwnerReading {
    /// Why a month is not complete (backend owner_ledger codes), in plain words.
    public static func incompleteReason(_ code: String, pendingMail: Int?, unclassified: Int?, language: AppLanguage = .current) -> String {
        // One is singular; zero, several and an unknown count ("algunos") are plural.
        switch code {
        case "pending_mail_review":
            if pendingMail == 1 {
                return language.pick("Hay 1 aviso de correo de este mes sin revisar: su monto todavía no cuenta.",
                                     "There is 1 mail notice from this month not reviewed yet: its amount doesn’t count yet.")
            }
            let count = pendingMail.map(String.init) ?? language.pick("algunos", "some")
            return language.pick("Hay \(count) avisos de correo de este mes sin revisar: sus montos todavía no cuentan.",
                                 "There are \(count) mail notices from this month not reviewed yet: their amounts don’t count yet.")
        case "unclassified_movements":
            if unclassified == 1 {
                return language.pick("Hay 1 movimiento sin clasificar (por ejemplo una transferencia): no suma como ingreso ni como gasto.",
                                     "There is 1 unclassified movement (a transfer, for example): it counts neither as income nor as spending.")
            }
            let count = unclassified.map(String.init) ?? language.pick("algunos", "some")
            return language.pick("Hay \(count) movimientos sin clasificar (por ejemplo transferencias): no suman como ingreso ni como gasto.",
                                 "There are \(count) unclassified movements (transfers, for example): they count neither as income nor as spending.")
        case "payroll_without_deposit":
            return language.pick("Hay nómina registrada (horas extra o bonos) sin el depósito del salario de este mes.",
                                 "There is payroll recorded (overtime or bonuses) without this month’s salary deposit.")
        default:
            return language.pick("Falta información para cerrar este mes.", "Some information is missing to close this month.")
        }
    }

    /// How a month with nothing pending reads: no movements (unknown, not zero), in progress, or closed.
    public enum MonthState: Sendable, Equatable { case noMovements, inProgress, closed }

    public static func monthState(_ s: MonthlySummary, currentMonth: String) -> MonthState {
        if [s.income, s.expenses, s.grossExpenses, s.debtPaid, s.otherInflows].allSatisfy({ ($0 ?? 0) == 0 }) { return .noMovements }
        return s.period == currentMonth ? .inProgress : .closed
    }

    /// Gross payroll is worth showing when any part of it is not zero (the parts can cancel out in the total).
    public static func hasPayroll(_ p: PayrollAccrued) -> Bool {
        [p.overtimeGross, p.vghGross, p.bonusesGross, p.totalGross].contains { ($0 ?? 0) != 0 }
    }

    /// A `YYYY-MM` month as the analysis lists it ("oct 2026", "Oct 2026"); anything else as it came.
    /// Android: `OwnerReading.monthLabel`.
    public static func monthLabel(_ period: String, language: AppLanguage = .current) -> String {
        let parts = period.split(separator: "-")
        guard parts.count == 2, let month = Int(parts[1]), (1...12).contains(month), parts[0].count == 4 else { return period }
        let spanish = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "set", "oct", "nov", "dic"]
        let english = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        return "\(language.pick(spanish[month - 1], english[month - 1])) \(parts[0])"
    }

    /// The months of a series that are not complete yet, in calendar order.
    public static func incompleteMonths(_ flow: [TransactionAnalysis.MonthPoint]) -> [String] {
        flow.filter { $0.complete == false && !$0.month.isEmpty }.map(\.month)
    }

    /// A strategy's formula line, labelled for whose formula it is. The Owner's `income` line is the
    /// income still to come in the cycle (backend `remaining_income_current_cycle`), not the month's
    /// income; Users keep the shared label.
    public static func formulaLabel(_ key: String, plan: DashboardStrategy, language: AppLanguage = .current) -> String {
        guard plan.isOwnerScope else { return DistributionLabels.formula(key, language: language) }
        switch key {
        case "income": return language.pick("Ingresos por recibir en el ciclo", "Income still to come this cycle")
        case "cash_available_now": return language.pick("Efectivo en tu cuenta de distribución", "Cash in your distribution account")
        case "statement_spending": return language.pick("Gastos del período del estado de cuenta", "Spending in the statement period")
        case "new_spending_after_cut": return language.pick("Gastos después del corte", "Spending after the statement cut")
        default: return DistributionLabels.formula(key, language: language)
        }
    }
}
