import Foundation

// HS-1 — "Tu salud financiera" in simple words (VIP and the Owner): one word, the main reason and one
// thing to do, no score and no technical figures. From what the app already reads: a normal month
// (`FinancialReading.Normal`: what is left, the share saved and the share that goes to debts) and how
// many months the Salvavidas covers (`/vip/salvavidas` coverage_months). Fixed rules, not advice.
// Unknown is never zero: without a normal month there is no reading; an unknown Salvavidas is left out.
// Android twin: `HealthReading.kt`.

public enum HealthReading {
    public enum Level: String, Sendable { case good, fair, atRisk }

    public struct Reading: Equatable, Sendable {
        public let level: Level
        public let word: String
        public let reason: String
        public let action: String
    }

    public static func reading(_ normal: FinancialReading.Normal?, coverageMonths: Double?, language: AppLanguage = .current) -> Reading? {
        guard let normal else { return nil }
        let debtShare = FinancialReading.per100(normal.debtPaid, of: normal.income) ?? 0
        let savedShare = FinancialReading.per100(normal.saved, of: normal.income) ?? 0
        func make(_ level: Level, _ reason: String, _ action: String) -> Reading {
            let word = switch level {
            case .good: language.pick("Bien", "Good")
            case .fair: language.pick("Regular", "Fair")
            case .atRisk: language.pick("En riesgo", "At risk")
            }
            return Reading(level: level, word: word, reason: reason, action: action)
        }
        // "1,5" / "1.5" meses; a whole number without decimals.
        let months = coverageMonths.map { value -> String in
            let text = String(format: "%.1f", value).replacingOccurrences(of: ".0", with: "")
            return language == .spanish ? text.replacingOccurrences(of: ".", with: ",") : text
        }

        if normal.left < 0 {
            return make(.atRisk, language.pick("En un mes normal sale más plata de la que entra.", "In a normal month more money goes out than comes in."),
                         language.pick("Revisá tu gasto más grande en Resumen del mes y bajalo un poco.", "Check your biggest spending in Monthly summary and lower it a little."))
        }
        if debtShare >= 40 {
            return make(.atRisk, language.pick("Las deudas se llevan \(debtShare) de cada 100 que entran.", "Debts take \(debtShare) of every 100 that come in."),
                         language.pick("Probá en Plan → Escenarios si refinanciar o juntar deudas te baja la cuota.", "Try in Plan → Scenarios whether refinancing or consolidating lowers your payment."))
        }
        if let coverageMonths, coverageMonths < 0.5, let months {
            return make(.atRisk, language.pick("Tu Salvavidas cubre \(months) meses de tus obligaciones.", "Your emergency fund covers \(months) months of your obligations."),
                         language.pick("Apartá algo cada semana para tu Salvavidas hasta cubrir un mes.", "Put something aside every week for your emergency fund until it covers a month."))
        }
        if savedShare < 10 {
            return make(.fair, language.pick("Guardás \(savedShare) de cada 100 que entran.", "You save \(savedShare) of every 100 that come in."),
                         language.pick("Subí lo que guardás poco a poco hasta 10 de cada 100.", "Raise what you save little by little up to 10 of every 100."))
        }
        if debtShare >= 20 {
            return make(.fair, language.pick("Las deudas se llevan \(debtShare) de cada 100 que entran.", "Debts take \(debtShare) of every 100 that come in."),
                         language.pick("Lo que te sobre, mandalo a la deuda más cara.", "Send what is left to your most expensive debt."))
        }
        if let coverageMonths, coverageMonths < 3, let months {
            return make(.fair, language.pick("Tu Salvavidas cubre \(months) meses; lo ideal son tres.", "Your emergency fund covers \(months) months; three is the aim."),
                         language.pick("Seguí con tu aporte al Salvavidas hasta llegar a tres meses.", "Keep contributing to your emergency fund until it reaches three months."))
        }
        return make(.good, language.pick("Te sobra plata, guardás y tus deudas están bajo control.", "You have money left, you save and your debts are under control."),
                     language.pick("Seguí así y pensá en tu próxima meta.", "Keep it up and think about your next goal."))
    }
}
