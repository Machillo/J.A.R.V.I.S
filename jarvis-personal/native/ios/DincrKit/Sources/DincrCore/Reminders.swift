import Foundation

// NT-1 — reminders on the phone (local notifications, no server): what the app already knows,
// said before it happens. The day before a debt's payment day and a fixed expense's due day, the
// day of a Salvavidas automatic contribution, the day a locked savings block for a debt matures
// (the Owner's, DB-1), and the first day of a month ("your month closed").
// Only dates the user recorded (a debt without a payment day gives none); nothing is guessed. The
// app schedules them on the phone (`ReminderScheduler`); this file only decides which and when, so
// both apps say the same. Android twin: `Reminders.kt`.

public enum Reminders {
    /// One notification: when (a local date and hour) and what it says.
    public struct Reminder: Equatable, Sendable {
        public let id: String
        public let date: DateComponents
        public let title: String
        public let body: String
    }

    /// A bill paid every month on a day: a debt's installment or a fixed expense.
    public struct Bill: Equatable, Sendable {
        public enum Kind: String, Sendable { case debt, fixed }
        public let id: String
        public let kind: Kind
        public let name: String
        public let amount: Decimal?
        public let day: Int

        public init(id: String, kind: Kind, name: String, amount: Decimal?, day: Int) {
            self.id = id; self.kind = kind; self.name = name; self.amount = amount; self.day = day
        }
    }

    public static let morningHour = 9
    /// iOS keeps at most 64 pending notifications per app; the next ones are scheduled on the next refresh.
    public static let limit = 60

    /// The bills with a known day: active debts with an installment day, and fixed expenses with a due day.
    public static func bills(debts: [Debt], fixed: [Bill] = []) -> [Bill] {
        let fromDebts = debts.compactMap { debt -> Bill? in
            guard (debt.remainingAmount ?? 0) > 0, let day = debt.paymentDay, (1...31).contains(day) else { return nil }
            return Bill(id: "debt-\(debt.id)", kind: .debt, name: debt.name ?? "", amount: debt.monthlyPayment, day: day)
        }
        return fromDebts + fixed.filter { (1...31).contains($0.day) }
    }

    /// Every reminder from `today` (local) to `days` ahead, earliest first, at most `limit`.
    public static func plan(today: Date, bills: [Bill], saving: SalvavidasAutoContribution?,
                            blocks: [DebtSavingsBlocks.Block] = [], days: Int = 35,
                            calendar: Calendar = Calendar(identifier: .gregorian), format: MoneyFormat,
                            language: AppLanguage = .current) -> [Reminder] {
        let start = calendar.startOfDay(for: today)
        guard let end = calendar.date(byAdding: .day, value: days, to: start) else { return [] }
        var result: [(Date, Reminder)] = []

        // The day before each bill's due day, in this month and the next ones within the window.
        for bill in bills {
            for offset in 0...2 {
                guard let month = calendar.date(byAdding: .month, value: offset, to: start),
                      let due = dueDate(day: bill.day, inMonthOf: month, calendar: calendar),
                      let notify = calendar.date(byAdding: .day, value: -1, to: due),
                      notify >= start, notify < end else { continue }
                let amount = bill.amount.map { " (\(format.string($0)))" } ?? ""
                let title = bill.kind == .debt ? language.pick("Mañana vence una cuota", "A payment is due tomorrow")
                                               : language.pick("Mañana se paga un gasto fijo", "A fixed expense is due tomorrow")
                let body = bill.kind == .debt ? language.pick("\(bill.name)\(amount). Tenela lista.", "\(bill.name)\(amount). Have it ready.")
                                              : language.pick("\(bill.name)\(amount).", "\(bill.name)\(amount).")
                result.append((notify, Reminder(id: "dincr.reminder.\(bill.id).\(key(due, calendar))", date: at(notify, calendar), title: title, body: body)))
            }
        }

        // The Salvavidas automatic contributions inside the window.
        if let saving, saving.enabled == true, let amount = saving.amount, amount > 0, let first = day(saving.startDate, calendar) {
            let last = day(saving.endDate, calendar).map { min($0, end) } ?? end
            var index = 0
            while index < 400, let date = contribution(first, index: index, frequency: saving.frequency, calendar: calendar), date < last {
                if date >= start {
                    result.append((date, Reminder(id: "dincr.reminder.salvavidas.\(key(date, calendar))", date: at(date, calendar),
                                                  title: language.pick("Hoy toca tu aporte al Salvavidas", "Your emergency fund contribution is today"),
                                                  body: language.pick("\(format.string(amount)) para tu Salvavidas.", "\(format.string(amount)) for your emergency fund."))))
                }
                index += 1
            }
        }

        // The day each locked savings block matures: pay what it holds into its debt.
        for block in blocks {
            guard let date = day(block.maturityDate, calendar), date >= start, date < end else { continue }
            let debt = block.debtName ?? language.pick("tu deuda", "your debt")
            let total = format.string(block.totalAtMaturity ?? 0)
            result.append((date, Reminder(id: "dincr.reminder.block.\(block.id).\(key(date, calendar))", date: at(date, calendar),
                                          title: language.pick("Hoy vence tu ahorro bloqueado", "Your locked saving matures today"),
                                          body: language.pick("Abonale \(total) a \(debt).", "Pay \(total) into \(debt)."))))
        }

        // The first day of each next month: the month that ended.
        for offset in 1...2 {
            guard let month = calendar.date(byAdding: .month, value: offset, to: start),
                  let first = calendar.date(from: calendar.dateComponents([.year, .month], from: month)),
                  first >= start, first < end else { continue }
            result.append((first, Reminder(id: "dincr.reminder.month.\(key(first, calendar))", date: at(first, calendar),
                                           title: language.pick("Tu mes cerró", "Your month closed"),
                                           body: language.pick("Mirá cuánto entró, cuánto salió y cuánto guardaste.", "See what came in, what went out and what you saved."))))
        }

        return Array(result.sorted { $0.0 == $1.0 ? $0.1.id < $1.1.id : $0.0 < $1.0 }.map(\.1).prefix(limit))
    }

    /// The bill's day in that month; a day the month doesn't have is its last day (31 → 30 April).
    static func dueDate(day: Int, inMonthOf month: Date, calendar: Calendar) -> Date? {
        var parts = calendar.dateComponents([.year, .month], from: month)
        guard let first = calendar.date(from: parts), let range = calendar.range(of: .day, in: .month, for: first) else { return nil }
        parts.day = min(day, range.count)
        return calendar.date(from: parts)
    }

    static func contribution(_ first: Date, index: Int, frequency: String?, calendar: Calendar) -> Date? {
        switch frequency {
        case "weekly": calendar.date(byAdding: .day, value: 7 * index, to: first)
        case "biweekly": calendar.date(byAdding: .day, value: 14 * index, to: first)
        case "monthly": calendar.date(byAdding: .month, value: index, to: first)
        default: nil
        }
    }

    static func day(_ text: String?, _ calendar: Calendar) -> Date? {
        guard let text, text.count >= 10 else { return nil }
        let parts = text.prefix(10).split(separator: "-").compactMap { Int($0) }
        guard parts.count == 3 else { return nil }
        return calendar.date(from: DateComponents(year: parts[0], month: parts[1], day: parts[2]))
    }

    static func at(_ date: Date, _ calendar: Calendar) -> DateComponents {
        var parts = calendar.dateComponents([.year, .month, .day], from: date)
        parts.hour = morningHour
        parts.minute = 0
        return parts
    }

    static func key(_ date: Date, _ calendar: Calendar) -> String {
        let p = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", p.year ?? 0, p.month ?? 0, p.day ?? 0)
    }
}
