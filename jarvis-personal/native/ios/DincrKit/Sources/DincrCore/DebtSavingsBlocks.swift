import Foundation

// Plan → Ahorro para deudas (Owner only): locked savings blocks for the strategy's long debts. The
// backend (`GET /jarvis/premium/debt-savings-blocks`, finance/debt_savings_blocks.py) decides
// everything: which debt, how much every Thursday, for how long, what locking costs. This file only
// decodes it and says it in short sentences, so both apps say the same. Recording a block created at
// the bank (POST), removing one (DELETE) and, when it matures, recording what was paid into the debt
// (POST …/apply) are the Owner's explicit actions. Android twin:
// `DebtSavingsBlocks.kt`.

public struct DebtSavingsBlocks: Decodable, Sendable, Equatable {
    public struct DebtRef: Decodable, Sendable, Equatable {
        public let id: Int?
        public let name: String?
        public let remainingAmount: Decimal?
        public let interestRate: Decimal?
    }

    public struct Recommendation: Decodable, Sendable, Equatable {
        public let choice: String?
        public let reason: String?
    }

    public struct Proposal: Decodable, Sendable, Equatable {
        public let mode: String?
        public let debt: DebtRef?
        public let weeklyAmount: Decimal?
        public let contributions: Int?
        public let termMonths: Int?
        public let startDate: String?
        public let maturityDate: String?
        public let totalSaved: Decimal?
        public let abonoAmount: Decimal?
        public let balanceAtMaturity: Decimal?
        public let balanceAfterAbono: Decimal?
        public let lockCost: Decimal?
        public let recommendation: Recommendation?
    }

    public struct ShortDebt: Decodable, Sendable, Equatable {
        public let id: Int?
        public let name: String?
        public let payoffMonth: Int?
    }

    public struct Block: Decodable, Sendable, Equatable, Identifiable {
        public let id: String
        public let debtId: Int?
        public let debtName: String?
        public let mode: String?
        public let weeklyAmount: Decimal?
        public let startDate: String?
        public let maturityDate: String?
        public let termMonths: Int?
        public let contributionsTotal: Int?
        public let contributionsDone: Int?
        public let savedSoFar: Decimal?
        public let totalAtMaturity: Decimal?
        public let nextDate: String?
        public let matured: Bool?
    }

    public let status: String
    public let weeklySafeAmount: Decimal?
    public let committedWeekly: Decimal?
    public let proposal: Proposal?
    public let shortDebts: [ShortDebt]?
    public let blocks: [Block]?
    public let warnings: [String]?
}

/// `POST /jarvis/premium/debt-savings-blocks`: the block the Owner created at the bank.
public struct DebtSavingsBlockCreate: Encodable, Sendable, Equatable {
    public let debtId: Int
    public let weeklyAmount: Decimal
    public let startDate: String
    public let termMonths: Int
    public let mode: String?

    public init(debtId: Int, weeklyAmount: Decimal, startDate: String, termMonths: Int, mode: String?) {
        self.debtId = debtId; self.weeklyAmount = weeklyAmount; self.startDate = startDate; self.termMonths = termMonths; self.mode = mode
    }
}

/// `POST /jarvis/premium/debt-savings-blocks/{id}/apply`: what was paid into the debt and what the bank
/// did with it (a shorter term, or a lower installment: then the new one).
public struct DebtSavingsBlockApply: Encodable, Sendable, Equatable {
    public enum Outcome: String, Sendable, CaseIterable { case reduceTerm = "reduce_term", reduceInstallment = "reduce_installment" }
    public let amount: Decimal
    public let outcome: String
    public let newMonthlyPayment: Decimal?

    public init(amount: Decimal, outcome: Outcome, newMonthlyPayment: Decimal?) {
        self.amount = amount; self.outcome = outcome.rawValue
        self.newMonthlyPayment = outcome == .reduceInstallment ? newMonthlyPayment : nil
    }
}

/// The answer of `…/apply`: the block, closed, with what was applied.
public struct DebtSavingsBlockApplied: Decodable, Sendable, Equatable {
    public struct Applied: Decodable, Sendable, Equatable {
        public let amount: Decimal?
        public let outcome: String?
        public let newRemainingAmount: Decimal?
        public let leftOver: Decimal?
    }
    public struct ClosedBlock: Decodable, Sendable, Equatable { public let id: String; public let applied: Applied? }
    public let block: ClosedBlock
}

extension DincrService {
    public func applyDebtSavingsBlock(id: String, _ request: DebtSavingsBlockApply) async throws -> DebtSavingsBlockApplied {
        try await client.send("POST", "/jarvis/premium/debt-savings-blocks/\(id)/apply", body: request)
    }

    public func debtSavingsBlocks() async throws -> DebtSavingsBlocks { try await client.get("/jarvis/premium/debt-savings-blocks") }

    public func createDebtSavingsBlock(_ request: DebtSavingsBlockCreate) async throws {
        let _: Acknowledgement = try await client.send("POST", "/jarvis/premium/debt-savings-blocks", body: request)
    }

    public func cancelDebtSavingsBlock(id: String) async throws {
        let _: Acknowledgement = try await client.send("DELETE", "/jarvis/premium/debt-savings-blocks/\(id)")
    }
}

public enum DebtSavingsReading {
    /// "5 nov 2026" for a `YYYY-MM-DD` date.
    public static func dayLabel(_ date: String?, language: AppLanguage = .current) -> String {
        guard let date, date.count >= 10, let day = Int(date.dropFirst(8).prefix(2)) else { return "—" }
        return "\(day) \(OwnerReading.monthLabel(String(date.prefix(7)), language: language))"
    }

    /// The proposal's headline: "Ahorrá ₡13.500 cada jueves por 6 meses".
    public static func headline(_ proposal: DebtSavingsBlocks.Proposal, format: MoneyFormat, language: AppLanguage = .current) -> String {
        let amount = format.string(proposal.weeklyAmount ?? 0)
        let months = proposal.termMonths ?? 0
        return language.pick("Ahorrá \(amount) cada jueves por \(months) meses", "Save \(amount) every Thursday for \(months) months")
    }

    /// The proposal in short sentences, in reading order.
    public static func lines(_ state: DebtSavingsBlocks, format: MoneyFormat, language: AppLanguage = .current) -> [String] {
        guard let proposal = state.proposal else { return [] }
        let debt = proposal.debt?.name ?? language.pick("tu deuda", "your debt")
        var lines: [String] = []
        if proposal.mode == "presave", let shorts = state.shortDebts, !shorts.isEmpty {
            let names = shorts.compactMap(\.name).joined(separator: ", ")
            lines.append(language.pick("Mientras terminás de pagar \(names), vas guardando para \(debt).",
                                       "While you finish paying \(names), you save for \(debt)."))
        } else {
            lines.append(language.pick("Es para \(debt), la deuda que sigue en tu estrategia.", "It is for \(debt), the next debt in your strategy."))
        }
        lines.append(language.pick("Empieza el \(dayLabel(proposal.startDate, language: language)) y vence el \(dayLabel(proposal.maturityDate, language: language)).",
                                   "It starts on \(dayLabel(proposal.startDate, language: language)) and matures on \(dayLabel(proposal.maturityDate, language: language))."))
        let abono = format.string(proposal.abonoAmount ?? 0)
        if let after = proposal.balanceAfterAbono {
            lines.append(language.pick("Ese día le abonás \(abono) a \(debt) y te queda debiendo unos \(format.string(after)).",
                                       "That day you pay \(abono) into \(debt) and owe about \(format.string(after)) after it."))
        } else {
            lines.append(language.pick("Ese día le abonás \(abono) a \(debt).", "That day you pay \(abono) into \(debt)."))
        }
        if let cost = proposal.lockCost, cost > 0 {
            lines.append(language.pick("Bloquearlo te cuesta unos \(format.string(cost)) en intereses frente a abonar cada semana. Es el precio de no ver esa plata.",
                                       "Locking it costs about \(format.string(cost)) in interest against paying every week. It is the price of not seeing that money."))
        }
        lines.append(language.pick("Los intereses del ahorro no se cuentan: si llegan, son ganancia.",
                                   "The savings' interest is not counted: if it comes, it is a bonus."))
        return lines
    }

    /// What to ask the bank when the block matures.
    public static func recommendation(_ proposal: DebtSavingsBlocks.Proposal, language: AppLanguage = .current) -> String {
        let why = proposal.recommendation?.reason == "saves_interest"
            ? language.pick("así ahorrás más intereses", "it saves the most interest")
            : language.pick("así terminás antes", "you finish sooner")
        return language.pick("Al abonar, pedile al banco bajar el plazo: \(why). Si solo te deja bajar la cuota, la diferencia se suma a tu siguiente ahorro.",
                             "When you pay, ask the bank to shorten the term: \(why). If it only lowers the installment, the difference goes into your next saving.")
    }

    /// Why there is no proposal, or nil when there is one.
    public static func statusMessage(_ state: DebtSavingsBlocks, language: AppLanguage = .current) -> String? {
        switch state.status {
        case "proposal": return nil
        case "no_debts":
            return language.pick("No tenés deudas activas. Más adelante esto sirve para tus metas.", "You have no active debts. Later this can serve your goals.")
        case "short_debts_only":
            return language.pick("Tus deudas se terminan en 3 meses o menos: seguí pagándolas directo.", "Your debts end within 3 months: keep paying them directly.")
        case "pay_directly":
            return language.pick("Esa deuda se paga pronto con tus pagos normales: no conviene bloquear plata para ella.",
                                 "That debt is paid soon with your normal payments: locking money for it is not worth it.")
        default:
            if (state.committedWeekly ?? 0) > 0 {
                return language.pick("Tus ahorros bloqueados ya usan todo tu sobrante seguro de cada jueves.",
                                     "Your locked savings already use all of your safe Thursday surplus.")
            }
            return language.pick("Con tu salario sin extras no queda plata segura para bloquear.",
                                 "Your salary without extras leaves no safe money to lock.")
        }
    }

    /// The warnings the backend sent, in words.
    public static func warnings(_ state: DebtSavingsBlocks, language: AppLanguage = .current) -> [String] {
        (state.warnings ?? []).compactMap { code in
            switch code {
            case "average_income_estimated":
                language.pick("Algunos salarios de los últimos 3 meses son estimados.", "Some salaries of the last 3 months are estimates.")
            case "average_income_unknown":
                language.pick("No hay salarios de los últimos 3 meses: el plazo usa solo tu salario base.", "No salaries in the last 3 months: the term uses only your base salary.")
            case "interest_rate_unknown":
                language.pick("Alguna deuda no tiene tasa: el costo de bloquear puede ser mayor.", "Some debt has no rate: locking may cost more.")
            default: nil
            }
        }
    }

    /// After the abono: where the debt stands, and what was left over (more than the debt owed).
    public static func appliedMessage(_ applied: DebtSavingsBlockApplied.Applied?, format: MoneyFormat, language: AppLanguage = .current) -> String {
        guard let applied else { return language.pick("Listo: el abono quedó registrado.", "Done: the payment is recorded.") }
        var text = (applied.newRemainingAmount ?? 0) > 0
            ? language.pick("Listo: tu deuda quedó en \(format.string(applied.newRemainingAmount ?? 0)).",
                            "Done: your debt is now \(format.string(applied.newRemainingAmount ?? 0)).")
            : language.pick("Listo: terminaste de pagar esa deuda.", "Done: that debt is paid off.")
        if let left = applied.leftOver, left > 0 {
            text += language.pick(" Te sobraron \(format.string(left)): mandalos a tu siguiente deuda o al Salvavidas.",
                                  " \(format.string(left)) was left over: send it to your next debt or your emergency fund.")
        }
        return text
    }

    /// One block the Owner created: progress, or what to do when it matured.
    public static func blockLines(_ block: DebtSavingsBlocks.Block, format: MoneyFormat, language: AppLanguage = .current) -> [String] {
        let debt = block.debtName ?? language.pick("tu deuda", "your debt")
        let total = format.string(block.totalAtMaturity ?? 0)
        if block.matured == true {
            return [language.pick("Venció el \(dayLabel(block.maturityDate, language: language)): abonale \(total) a \(debt).",
                                  "It matured on \(dayLabel(block.maturityDate, language: language)): pay \(total) into \(debt).")]
        }
        return [
            language.pick("\(format.string(block.weeklyAmount ?? 0)) cada jueves", "\(format.string(block.weeklyAmount ?? 0)) every Thursday"),
            language.pick("Llevás \(format.string(block.savedSoFar ?? 0)) de \(total) (\(block.contributionsDone ?? 0) de \(block.contributionsTotal ?? 0) jueves).",
                          "\(format.string(block.savedSoFar ?? 0)) of \(total) so far (\(block.contributionsDone ?? 0) of \(block.contributionsTotal ?? 0) Thursdays)."),
            language.pick("Vence el \(dayLabel(block.maturityDate, language: language)).", "Matures on \(dayLabel(block.maturityDate, language: language))."),
        ]
    }
}
