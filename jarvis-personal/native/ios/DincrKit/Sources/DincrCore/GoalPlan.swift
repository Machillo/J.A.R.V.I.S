import Foundation

// GO-1 — every goal says, in plain words, what it takes: how much per month to reach it by its date,
// and (VIP and the Owner) how long it takes with what is left in a normal month
// (`FinancialReading.Normal.left`). Only known amounts are used: an unknown amount saved says nothing.
// Android twin: `GoalPlan.kt`.

public enum GoalPlan {
    /// What is left over the months until the target date's month (at least one); nil without a
    /// future date or with nothing left. The current month counts as one of them.
    public static func monthlyNeeded(_ goal: Goal, today: Date, calendar: Calendar = Calendar(identifier: .gregorian)) -> Decimal? {
        guard let remaining = goal.remaining, remaining > 0, let months = monthsUntil(goal.targetDate, today: today, calendar: calendar), months >= 0 else { return nil }
        return rounded(remaining / Decimal(max(months, 1)))
    }

    /// The goal's plan in one or two short lines.
    public static func lines(_ goal: Goal, today: Date, normalLeft: Decimal?, format: MoneyFormat,
                             calendar: Calendar = Calendar(identifier: .gregorian), language: AppLanguage = .current) -> [String] {
        if goal.status == "completed" || goal.remaining == 0 { return [language.pick("¡Meta cumplida!", "Goal reached!")] }
        guard let remaining = goal.remaining else { return [] }
        var lines: [String] = []
        if let months = monthsUntil(goal.targetDate, today: today, calendar: calendar), let date = goal.targetDate {
            let month = OwnerReading.monthLabel(String(date.prefix(7)), language: language)
            if months < 0 {
                lines.append(language.pick("La fecha ya pasó y te faltan \(format.string(remaining)). Cambiala para recalcular.",
                                           "The date has passed and \(format.string(remaining)) is still missing. Change it to recalculate."))
            } else if let needed = monthlyNeeded(goal, today: today, calendar: calendar) {
                lines.append(language.pick("Para llegar en \(month) necesitás \(format.string(needed)) por mes.",
                                           "To get there by \(month) you need \(format.string(needed)) a month."))
            }
        } else {
            lines.append(language.pick("Poné una fecha para saber cuánto guardar por mes.", "Set a date to know how much to save each month."))
        }
        if let left = normalLeft {
            if left > 0 {
                let months = NSDecimalNumber(decimal: remaining / left).doubleValue.rounded(.up)
                lines.append(language.pick("Con lo que te sobra en un mes normal (\(format.string(left))) llegás en \(Int(months)) \(months == 1 ? "mes" : "meses").",
                                           "With what is left in a normal month (\(format.string(left))) you get there in \(Int(months)) \(months == 1 ? "month" : "months")."))
            } else {
                lines.append(language.pick("Hoy no te sobra plata en un mes normal: primero hay que liberar algo.",
                                           "Nothing is left in a normal month today: something has to be freed first."))
            }
        }
        return lines
    }

    /// Whole months from this month to the date's month; nil without a date.
    static func monthsUntil(_ date: String?, today: Date, calendar: Calendar) -> Int? {
        guard let date, date.count >= 7 else { return nil }
        let parts = date.prefix(7).split(separator: "-").compactMap { Int($0) }
        guard parts.count == 2 else { return nil }
        let now = calendar.dateComponents([.year, .month], from: today)
        return (parts[0] - (now.year ?? 0)) * 12 + (parts[1] - (now.month ?? 0))
    }

    private static func rounded(_ value: Decimal) -> Decimal {
        var copy = value, result = Decimal()
        NSDecimalRound(&result, &copy, 2, .plain)
        return result
    }
}
